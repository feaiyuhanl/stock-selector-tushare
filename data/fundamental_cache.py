"""
基本面和财务数据缓存模块
"""
import pandas as pd
import sqlite3
import threading
import time
from datetime import datetime
from typing import Dict, Optional


class FundamentalCache:
    """基本面和财务数据缓存管理器"""
    
    def __init__(self, base):
        """
        初始化基本面和财务数据缓存管理器
        Args:
            base: CacheBase实例，提供基础功能
        """
        self.base = base
        
        # 内存缓存（优化：避免重复读取数据库）
        # 格式: {stock_code: data_dict}
        self._fundamental_cache_memory: Optional[Dict[str, Dict]] = None
        self._financial_cache_memory: Optional[Dict[str, Dict]] = None
        self._fundamental_cache_lock = threading.Lock()  # 保护内存缓存的读取和初始化
        self._financial_cache_lock = threading.Lock()

        # 数据类型配置（用于统一处理fundamental和financial）
        self._data_type_config = {
            'fundamental': {
                'table': 'fundamental_data',
                'fields': ['pe_ratio', 'pb_ratio', 'roe', 'revenue_growth', 'profit_growth'],
                'memory_cache_attr': '_fundamental_cache_memory',
                'lock_attr': '_fundamental_cache_lock',
                'db_lock_key': 'fundamental',
                'valid_days': 7,
            },
            'financial': {
                'table': 'financial_data',
                'fields': ['roe'],
                'memory_cache_attr': '_financial_cache_memory',
                'lock_attr': '_financial_cache_lock',
                'db_lock_key': 'financial',
                'valid_days': 7,
            }
        }
    
    def _get_cached_data(self, data_type: str, stock_code: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        统一的缓存数据获取方法（内部使用）
        Args:
            data_type: 数据类型 ('fundamental', 'financial')
            stock_code: 股票代码
            force_refresh: 是否强制刷新
        Returns:
            数据字典
        """
        config = self._data_type_config[data_type]
        
        if force_refresh:
            # 强制刷新时，清除内存缓存
            lock = getattr(self, config['lock_attr'])
            memory_cache = getattr(self, config['memory_cache_attr'])
            with lock:
                setattr(self, config['memory_cache_attr'], None)
            return None

        # 标准化股票代码
        stock_code = self.base._normalize_stock_code(stock_code)

        # 优化：优先从内存缓存读取
        lock = getattr(self, config['lock_attr'])
        memory_cache = getattr(self, config['memory_cache_attr'])
        
        with lock:
            if memory_cache is not None:
                # 内存缓存已加载，直接返回
                data = memory_cache.get(stock_code)
                if data is not None:
                    # 验证数据有效性
                    if self.base._is_data_valid(data, data_type):
                        return data.copy()  # 返回副本，避免外部修改影响缓存
                return None

            # 内存缓存未加载，需要从数据库加载
            if self.base._is_cache_valid(data_type, stock_code):
                try:
                    with sqlite3.connect(self.base.db_path) as conn:
                        # 查询所有数据到内存缓存
                        valid_days = config['valid_days']
                        df = pd.read_sql_query(f'''
                            SELECT * FROM {config['table']}
                            WHERE update_time >= datetime('now', '-{valid_days} day')
                        ''', conn)

                        # 加载到内存缓存
                        new_cache = {}
                        for _, row in df.iterrows():
                            code = self.base._normalize_stock_code(row['code'])
                            data = row.to_dict()
                            # 移除数据库特有的字段
                            data.pop('created_time', None)
                            if self.base._is_data_valid(data, data_type):
                                new_cache[code] = data
                        
                        setattr(self, config['memory_cache_attr'], new_cache)

                        # 从内存缓存获取当前股票的数据
                        data = new_cache.get(stock_code)
                        if data is not None:
                            return data.copy()  # 返回副本

                except Exception as e:
                    print(f"读取{data_type}缓存失败: {e}")
                    # 清除内存缓存，避免下次继续失败
                    setattr(self, config['memory_cache_attr'], None)

        return None
    
    def _save_cached_data(self, data_type: str, stock_code: str, data: Dict):
        """
        统一的缓存数据保存方法（内部使用）
        Args:
            data_type: 数据类型 ('fundamental', 'financial')
            stock_code: 股票代码
            data: 数据字典
        """
        config = self._data_type_config[data_type]
        
        # 使用数据库锁防止并发写入
        with self.base._db_locks[config['db_lock_key']]:
            try:
                # 验证数据有效性
                if not self.base._is_data_valid(data, data_type):
                    return  # 无效数据不保存

                stock_code = self.base._normalize_stock_code(stock_code)
                update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                with sqlite3.connect(self.base.db_path) as conn:
                    cursor = conn.cursor()

                    # 构建SQL语句
                    fields = config['fields']
                    placeholders = ', '.join(['?'] * (len(fields) + 2))  # +2 for code and update_time
                    field_names = ', '.join(['code'] + fields + ['update_time'])
                    values = [stock_code] + [data.get(field) for field in fields] + [update_time]

                    # 插入或更新数据
                    cursor.execute(f'''
                        INSERT OR REPLACE INTO {config['table']}
                        ({field_names})
                        VALUES ({placeholders})
                    ''', values)

                    conn.commit()

                    # 优化：更新内存缓存（如果已加载）
                    lock = getattr(self, config['lock_attr'])
                    memory_cache = getattr(self, config['memory_cache_attr'])
                    with lock:
                        if memory_cache is not None:
                            # 更新内存缓存中的数据
                            cache_data = data.copy()
                            memory_cache[stock_code] = cache_data

            except Exception as e:
                print(f"保存{data_type}缓存失败: {e}")
    
    def _batch_save_cached_data(self, data_type: str, data_dict: Dict[str, Dict]):
        """
        统一的批量保存缓存数据方法（内部使用，带重试机制）
        Args:
            data_type: 数据类型 ('fundamental', 'financial')
            data_dict: {stock_code: data_dict} 字典
        """
        config = self._data_type_config[data_type]
        
        if not data_dict:
            return
        
        # 使用数据库锁防止并发写入
        with self.base._db_locks[config['db_lock_key']]:
            # 重试机制：最多重试3次，每次间隔递增
            max_retries = 3
            retry_delay = 0.1  # 初始延迟0.1秒
            
            for attempt in range(max_retries):
                try:
                    # 过滤有效数据
                    valid_data = {}
                    for stock_code, data in data_dict.items():
                        if self.base._is_data_valid(data, data_type):
                            valid_data[stock_code] = data
                    
                    if not valid_data:
                        return
                    
                    stock_codes = [self.base._normalize_stock_code(code) for code in valid_data.keys()]
                    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 使用带超时的连接
                    with self.base._get_db_connection(timeout=30.0) as conn:
                        cursor = conn.cursor()
                        
                        # 批量插入数据
                        fields = config['fields']
                        data_to_insert = []
                        for stock_code, data in valid_data.items():
                            stock_code = self.base._normalize_stock_code(stock_code)
                            values = [stock_code] + [data.get(field) for field in fields] + [update_time]
                            data_to_insert.append(tuple(values))
                        
                        # 使用executemany批量插入
                        placeholders = ', '.join(['?'] * (len(fields) + 2))
                        field_names = ', '.join(['code'] + fields + ['update_time'])
                        cursor.executemany(f'''
                            INSERT OR REPLACE INTO {config['table']}
                            ({field_names})
                            VALUES ({placeholders})
                        ''', data_to_insert)
                        
                        conn.commit()
                    
                    # 优化：更新内存缓存（如果已加载）
                    lock = getattr(self, config['lock_attr'])
                    memory_cache = getattr(self, config['memory_cache_attr'])
                    with lock:
                        if memory_cache is not None:
                            # 更新内存缓存中的数据
                            for stock_code, data in valid_data.items():
                                stock_code = self.base._normalize_stock_code(stock_code)
                                memory_cache[stock_code] = data.copy()
                    
                    # 成功保存，退出重试循环
                    return
                    
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e).lower():
                        if attempt < max_retries - 1:
                            # 等待后重试
                            time.sleep(retry_delay * (attempt + 1))  # 递增延迟
                            continue
                        else:
                            # 最后一次重试也失败
                            print(f"批量保存{data_type}缓存失败: 数据库锁定，已重试{max_retries}次")
                            return
                    else:
                        # 其他OperationalError，直接抛出
                        print(f"批量保存{data_type}缓存失败: {e}")
                        return
                except Exception as e:
                    print(f"批量保存{data_type}缓存失败: {e}")
                    return
    
    def get_fundamental(self, stock_code: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        从缓存获取基本面数据（优先从内存缓存读取，避免重复读取数据库）
        Args:
            stock_code: 股票代码
            force_refresh: 是否强制刷新
        Returns:
            基本面数据字典
        """
        return self._get_cached_data('fundamental', stock_code, force_refresh)
    
    def save_fundamental(self, stock_code: str, data: Dict):
        """
        保存基本面数据到缓存
        Args:
            stock_code: 股票代码
            data: 基本面数据
        """
        self._save_cached_data('fundamental', stock_code, data)
    
    def batch_save_fundamental(self, data_dict: Dict[str, Dict]):
        """
        批量保存基本面数据（提高效率，使用SQLite事务）
        Args:
            data_dict: {stock_code: data_dict} 字典
        """
        self._batch_save_cached_data('fundamental', data_dict)
    
    def get_financial(self, stock_code: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        从缓存获取财务数据（优先从内存缓存读取，避免重复读取数据库）
        Args:
            stock_code: 股票代码
            force_refresh: 是否强制刷新
        Returns:
            财务数据字典
        """
        return self._get_cached_data('financial', stock_code, force_refresh)
    
    def save_financial(self, stock_code: str, data: Dict):
        """
        保存财务数据到缓存
        Args:
            stock_code: 股票代码
            data: 财务数据
        """
        self._save_cached_data('financial', stock_code, data)
    
    def batch_save_financial(self, data_dict: Dict[str, Dict]):
        """
        批量保存财务数据（提高效率，使用SQLite事务）
        Args:
            data_dict: {stock_code: data_dict} 字典
        """
        self._batch_save_cached_data('financial', data_dict)

