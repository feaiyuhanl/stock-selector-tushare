"""
缓存管理模块：管理本地SQLite缓存
"""
import pandas as pd
import os
import glob
import threading
import time
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import config
import json


class CacheManager:
    """缓存管理器 - SQLite实现"""

    def __init__(self, cache_dir: str = "cache"):
        """
        初始化缓存管理器
        Args:
            cache_dir: 缓存目录
        """
        self.cache_dir = cache_dir
        self._ensure_cache_dir()

        # SQLite数据库文件路径
        self.db_path = os.path.join(cache_dir, "stock_cache.db")

        # 缓存有效期（天数）
        # 说明：超过有效期后，缓存自动失效，会重新从API获取数据
        self.cache_valid_days = {
            'fundamental': 7,      # 缓存有效期7天（超过7天自动失效）
            'financial': 7,        # 缓存有效期7天（超过7天自动失效）
            'sectors': 7,          # 缓存有效期7天（超过7天自动失效）
            'concepts': 7,         # 缓存有效期7天（超过7天自动失效）
            'stock_list': 1,       # 缓存有效期1天（超过1天自动失效）
            'kline': 1,            # 缓存有效期1天（必须是今天，否则失效）
            'trade_calendar': 7,   # 交易日历缓存有效期7天（每周刷新一次）
        }

        # 定义哪些数据类型是低频的（变化频率低，但缓存失效后仍会重新获取）
        self.low_frequency_types = ['financial', 'sectors', 'concepts']

        # 数据库级别的锁，防止并发写入
        self._db_locks = {
            'fundamental': threading.Lock(),
            'financial': threading.Lock(),
            'sectors': threading.Lock(),
            'concepts': threading.Lock(),
            'stock_list': threading.Lock(),
            'kline': threading.Lock(),
        }

        # 内存缓存（优化：避免重复读取数据库）
        # 格式: {stock_code: data_dict}
        self._fundamental_cache_memory: Optional[Dict[str, Dict]] = None
        self._financial_cache_memory: Optional[Dict[str, Dict]] = None
        self._fundamental_cache_lock = threading.Lock()  # 保护内存缓存的读取和初始化
        self._financial_cache_lock = threading.Lock()

        # 初始化数据库
        self._init_database()

    def _init_database(self):
        """初始化SQLite数据库和表结构"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 创建基本面数据表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fundamental_data (
                    code TEXT PRIMARY KEY,
                    pe_ratio REAL,
                    pb_ratio REAL,
                    roe REAL,
                    revenue_growth REAL,
                    profit_growth REAL,
                    update_time TEXT NOT NULL,
                    created_time TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 创建财务数据表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS financial_data (
                    code TEXT PRIMARY KEY,
                    roe REAL,
                    update_time TEXT NOT NULL,
                    created_time TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 创建板块数据表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stock_sectors (
                    code TEXT PRIMARY KEY,
                    sectors TEXT,  -- JSON格式存储板块列表
                    update_time TEXT NOT NULL,
                    created_time TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 创建概念数据表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stock_concepts (
                    code TEXT PRIMARY KEY,
                    concepts TEXT,  -- JSON格式存储概念列表
                    update_time TEXT NOT NULL,
                    created_time TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 创建股票列表表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stock_list (
                    code TEXT PRIMARY KEY,
                    name TEXT,
                    market TEXT,
                    area TEXT,
                    industry TEXT,
                    list_date TEXT,
                    update_time TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 创建K线数据表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS kline_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    cache_type TEXT NOT NULL,  -- 'stock', 'sector', 'concept'
                    period TEXT NOT NULL,      -- 'daily', 'weekly', 'monthly'
                    date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    amount REAL,
                    update_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, cache_type, period, date)
                )
            ''')
            
            # 创建交易日历表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trade_calendar (
                    cal_date TEXT PRIMARY KEY,  -- 日期，格式：YYYYMMDD
                    is_open INTEGER NOT NULL,   -- 是否交易日：1=交易日，0=非交易日
                    update_time TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 创建索引以提高查询性能
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_fundamental_code ON fundamental_data(code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_financial_code ON financial_data(code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sectors_code ON stock_sectors(code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_concepts_code ON stock_concepts(code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_stock_list_code ON stock_list(code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_kline_symbol_type_period ON kline_data(symbol, cache_type, period)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_kline_date ON kline_data(date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_trade_calendar_date ON trade_calendar(cal_date)')

            conn.commit()

    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
    
    def _is_cache_valid(self, cache_type: str, stock_code: str = None) -> bool:
        """
        检查缓存是否有效
        Args:
            cache_type: 缓存类型
            stock_code: 股票代码（对于需要按股票检查的缓存）
        Returns:
            是否有效
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                if cache_type == 'kline':
                    # K线数据检查最新的记录时间
                    cursor.execute('''
                        SELECT MAX(date) FROM kline_data
                        WHERE update_time >= date('now', '-1 day')
                    ''')
                else:
                    # 其他数据类型检查是否有有效记录
                    table_map = {
                        'fundamental': 'fundamental_data',
                        'financial': 'financial_data',
                        'sectors': 'stock_sectors',
                        'concepts': 'stock_concepts',
                        'stock_list': 'stock_list',
                        'trade_calendar': 'trade_calendar'
                    }

                    if cache_type not in table_map:
                        return False

                    table_name = table_map[cache_type]
                    valid_days = self.cache_valid_days.get(cache_type, 7)

                    if stock_code:
                        # 检查特定股票的数据是否有效
                        cursor.execute(f'''
                            SELECT COUNT(*) FROM {table_name}
                            WHERE code = ? AND update_time >= datetime('now', '-{valid_days} day')
                        ''', (stock_code,))
                    else:
                        # 检查表中是否有有效数据
                        cursor.execute(f'''
                            SELECT COUNT(*) FROM {table_name}
                            WHERE update_time >= datetime('now', '-{valid_days} day')
                        ''')

                result = cursor.fetchone()
                return result and result[0] > 0

        except Exception as e:
            print(f"检查缓存有效性失败 ({cache_type}): {e}")
            return False
    
    
    def _is_data_valid(self, data: Dict, data_type: str) -> bool:
        """
        检查数据是否有效（关键指标不为空）
        优化：区分0值（可能是正常值）和None值（数据缺失）
        Args:
            data: 数据字典
            data_type: 数据类型 ('fundamental', 'financial')
        Returns:
            是否有效
        """
        if not data or not isinstance(data, dict):
            return False

        if data_type == 'fundamental':
            # 基本面数据：至少需要pe_ratio或pb_ratio之一有效（不为None）
            # 改进：区分0值（可能是正常值，如亏损股的PE=0）和None值（数据缺失）
            pe = data.get('pe_ratio')
            pb = data.get('pb_ratio')

            # 如果两个都是None，视为无效（数据缺失）
            # 如果至少有一个不是None（即使是0），视为有效
            if pe is None and pb is None:
                return False
            return True
        elif data_type == 'financial':
            # 财务数据：至少需要roe有效（不为None）
            roe = data.get('roe')
            if roe is None:
                return False
            return True

        return True
    
    def get_fundamental(self, stock_code: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        从缓存获取基本面数据（优先从内存缓存读取，避免重复读取数据库）
        Args:
            stock_code: 股票代码
            force_refresh: 是否强制刷新
        Returns:
            基本面数据字典
        """
        if force_refresh:
            # 强制刷新时，清除内存缓存
            with self._fundamental_cache_lock:
                self._fundamental_cache_memory = None
            return None

        # 确保代码格式化为6位字符串
        stock_code = str(stock_code).zfill(6)

        # 优化：优先从内存缓存读取
        with self._fundamental_cache_lock:
            if self._fundamental_cache_memory is not None:
                # 内存缓存已加载，直接返回
                data = self._fundamental_cache_memory.get(stock_code)
                if data is not None:
                    # 验证数据有效性
                    if self._is_data_valid(data, 'fundamental'):
                        return data.copy()  # 返回副本，避免外部修改影响缓存
                return None

            # 内存缓存未加载，需要从数据库加载
            if self._is_cache_valid('fundamental', stock_code):
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        # 查询所有基本面数据到内存缓存
                        df = pd.read_sql_query('''
                            SELECT * FROM fundamental_data
                            WHERE update_time >= datetime('now', '-7 day')
                        ''', conn)

                        # 加载到内存缓存
                        self._fundamental_cache_memory = {}
                        for _, row in df.iterrows():
                            code = str(row['code']).zfill(6)
                            data = row.to_dict()
                            # 移除数据库特有的字段
                            data.pop('created_time', None)
                            if self._is_data_valid(data, 'fundamental'):
                                self._fundamental_cache_memory[code] = data

                        # 从内存缓存获取当前股票的数据
                        data = self._fundamental_cache_memory.get(stock_code)
                        if data is not None:
                            return data.copy()  # 返回副本

                except Exception as e:
                    print(f"读取基本面缓存失败: {e}")
                    # 清除内存缓存，避免下次继续失败
                    self._fundamental_cache_memory = None

        return None
    
    def save_fundamental(self, stock_code: str, data: Dict):
        """
        保存基本面数据到缓存
        Args:
            stock_code: 股票代码
            data: 基本面数据
        """
        # 使用数据库锁防止并发写入
        with self._db_locks['fundamental']:
            try:
                # 验证数据有效性
                if not self._is_data_valid(data, 'fundamental'):
                    return  # 无效数据不保存

                stock_code = str(stock_code).zfill(6)
                update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # 插入或更新数据
                    cursor.execute('''
                        INSERT OR REPLACE INTO fundamental_data
                        (code, pe_ratio, pb_ratio, roe, revenue_growth, profit_growth, update_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        stock_code,
                        data.get('pe_ratio'),
                        data.get('pb_ratio'),
                        data.get('roe'),
                        data.get('revenue_growth'),
                        data.get('profit_growth'),
                        update_time
                    ))

                    conn.commit()

                    # 优化：更新内存缓存（如果已加载）
                    with self._fundamental_cache_lock:
                        if self._fundamental_cache_memory is not None:
                            # 更新内存缓存中的数据
                            cache_data = data.copy()
                            self._fundamental_cache_memory[stock_code] = cache_data

            except Exception as e:
                print(f"保存基本面缓存失败: {e}")
    
    def batch_save_fundamental(self, data_dict: Dict[str, Dict]):
        """
        批量保存基本面数据（提高效率，使用SQLite事务）
        Args:
            data_dict: {stock_code: data_dict} 字典
        """
        if not data_dict:
            return

        # 添加重试机制处理并发冲突
        max_batch_retries = 3
        for batch_attempt in range(max_batch_retries):
            try:
                # 使用数据库锁防止并发写入
                with self._db_locks['fundamental']:
                    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()

                        # 准备批量插入数据
                        data_to_insert = []
                        for stock_code, data in data_dict.items():
                            # 验证数据有效性
                            if not self._is_data_valid(data, 'fundamental'):
                                continue

                            stock_code = str(stock_code).zfill(6)
                            data_to_insert.append((
                                stock_code,
                                data.get('pe_ratio'),
                                data.get('pb_ratio'),
                                data.get('roe'),
                                data.get('revenue_growth'),
                                data.get('profit_growth'),
                                update_time
                            ))

                        if data_to_insert:
                            # 使用INSERT OR REPLACE进行批量更新
                            cursor.executemany('''
                                INSERT OR REPLACE INTO fundamental_data
                                (code, pe_ratio, pb_ratio, roe, revenue_growth, profit_growth, update_time)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', data_to_insert)

                            conn.commit()

                            # 优化：更新内存缓存（如果已加载）
                            with self._fundamental_cache_lock:
                                if self._fundamental_cache_memory is not None:
                                    # 更新内存缓存中的数据
                                    for stock_code, data in data_dict.items():
                                        clean_code = str(stock_code).zfill(6)
                                        if self._is_data_valid(data, 'fundamental'):
                                            cache_data = data.copy()
                                            self._fundamental_cache_memory[clean_code] = cache_data

                break  # 成功后退出重试循环

            except Exception as e:
                print(f"批量保存基本面缓存失败 (尝试 {batch_attempt + 1}/{max_batch_retries}): {e}")
                # 记录更详细的错误信息
                import traceback
                print(f"错误详情: {traceback.format_exc()}")

                # 如果不是最后一次尝试，等待后重试
                if batch_attempt < max_batch_retries - 1:
                    wait_time = (batch_attempt + 1) * 0.5  # 递增等待时间
                    print(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    continue
                else:
                    # 最后一次尝试失败，记录错误但不抛出异常
                    print(f"批量保存基本面缓存失败，已达到最大重试次数: {e}")
                    return
    
    def get_financial(self, stock_code: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        从缓存获取财务数据（优先从内存缓存读取，避免重复读取数据库）
        Args:
            stock_code: 股票代码
            force_refresh: 是否强制刷新
        Returns:
            财务数据字典
        """
        if force_refresh:
            # 强制刷新时，清除内存缓存
            with self._financial_cache_lock:
                self._financial_cache_memory = None
            return None

        # 确保代码格式化为6位字符串
        stock_code = str(stock_code).zfill(6)

        # 优化：优先从内存缓存读取
        with self._financial_cache_lock:
            if self._financial_cache_memory is not None:
                # 内存缓存已加载，直接返回
                data = self._financial_cache_memory.get(stock_code)
                if data is not None:
                    # 验证数据有效性
                    if self._is_data_valid(data, 'financial'):
                        return data.copy()  # 返回副本，避免外部修改影响缓存
                return None

            # 内存缓存未加载，需要从数据库加载
            if self._is_cache_valid('financial', stock_code):
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        # 查询所有财务数据到内存缓存
                        df = pd.read_sql_query('''
                            SELECT * FROM financial_data
                            WHERE update_time >= datetime('now', '-7 day')
                        ''', conn)

                        # 加载到内存缓存
                        self._financial_cache_memory = {}
                        for _, row in df.iterrows():
                            code = str(row['code']).zfill(6)
                            data = row.to_dict()
                            # 移除数据库特有的字段
                            data.pop('created_time', None)
                            if self._is_data_valid(data, 'financial'):
                                self._financial_cache_memory[code] = data

                        # 从内存缓存获取当前股票的数据
                        data = self._financial_cache_memory.get(stock_code)
                        if data is not None:
                            return data.copy()  # 返回副本

                except Exception as e:
                    print(f"读取财务缓存失败: {e}")
                    # 清除内存缓存，避免下次继续失败
                    self._financial_cache_memory = None

        return None
    
    def save_financial(self, stock_code: str, data: Dict):
        """
        保存财务数据到缓存
        Args:
            stock_code: 股票代码
            data: 财务数据
        """
        # 使用数据库锁防止并发写入
        with self._db_locks['financial']:
            try:
                # 验证数据有效性
                if not self._is_data_valid(data, 'financial'):
                    return  # 无效数据不保存

                stock_code = str(stock_code).zfill(6)
                update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # 插入或更新数据
                    cursor.execute('''
                        INSERT OR REPLACE INTO financial_data
                        (code, roe, update_time)
                        VALUES (?, ?, ?)
                    ''', (
                        stock_code,
                        data.get('roe'),
                        update_time
                    ))

                    conn.commit()

                    # 优化：更新内存缓存（如果已加载）
                    with self._financial_cache_lock:
                        if self._financial_cache_memory is not None:
                            # 更新内存缓存中的数据
                            cache_data = data.copy()
                            self._financial_cache_memory[stock_code] = cache_data

            except Exception as e:
                print(f"保存财务缓存失败: {e}")
    
    def batch_save_financial(self, data_dict: Dict[str, Dict]):
        """
        批量保存财务数据（提高效率，使用SQLite事务）
        Args:
            data_dict: {stock_code: data_dict} 字典
        """
        if not data_dict:
            return

        # 添加重试机制处理并发冲突
        max_batch_retries = 3
        for batch_attempt in range(max_batch_retries):
            try:
                # 使用数据库锁防止并发写入
                with self._db_locks['financial']:
                    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()

                        # 准备批量插入数据
                        data_to_insert = []
                        for stock_code, data in data_dict.items():
                            # 验证数据有效性
                            if not self._is_data_valid(data, 'financial'):
                                continue

                            stock_code = str(stock_code).zfill(6)
                            data_to_insert.append((
                                stock_code,
                                data.get('roe'),
                                update_time
                            ))

                        if data_to_insert:
                            # 使用INSERT OR REPLACE进行批量更新
                            cursor.executemany('''
                                INSERT OR REPLACE INTO financial_data
                                (code, roe, update_time)
                                VALUES (?, ?, ?)
                            ''', data_to_insert)

                            conn.commit()

                            # 优化：更新内存缓存（如果已加载）
                            with self._financial_cache_lock:
                                if self._financial_cache_memory is not None:
                                    # 更新内存缓存中的数据
                                    for stock_code, data in data_dict.items():
                                        clean_code = str(stock_code).zfill(6)
                                        if self._is_data_valid(data, 'financial'):
                                            cache_data = data.copy()
                                            self._financial_cache_memory[clean_code] = cache_data

                break  # 成功后退出重试循环

            except Exception as e:
                print(f"批量保存财务缓存失败 (尝试 {batch_attempt + 1}/{max_batch_retries}): {e}")
                # 记录更详细的错误信息
                import traceback
                print(f"错误详情: {traceback.format_exc()}")

                # 如果不是最后一次尝试，等待后重试
                if batch_attempt < max_batch_retries - 1:
                    wait_time = (batch_attempt + 1) * 0.5  # 递增等待时间
                    print(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    continue
                else:
                    # 最后一次尝试失败，记录错误但不抛出异常
                    print(f"批量保存财务缓存失败，已达到最大重试次数: {e}")
                    return
    
    def get_stock_sectors(self, stock_code: str, force_refresh: bool = False) -> Optional[List[str]]:
        """
        从缓存获取股票板块
        Args:
            stock_code: 股票代码
            force_refresh: 是否强制刷新
        Returns:
            板块列表，如果缓存中没有数据返回None，如果缓存中保存了空列表返回[]
        """
        if force_refresh:
            return None

        stock_code = str(stock_code).zfill(6)

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 查询板块数据
                cursor.execute('''
                    SELECT sectors, update_time FROM stock_sectors
                    WHERE code = ? AND update_time >= datetime('now', '-7 day')
                ''', (stock_code,))

                result = cursor.fetchone()
                if result:
                    sectors_str, update_time_str = result

                    # 如果sectors字段存在但为空字符串，说明之前保存了空列表
                    if sectors_str == '':
                        # 检查缓存时间，如果超过3天，返回None让fetcher重新获取
                        try:
                            update_time = datetime.strptime(update_time_str, '%Y-%m-%d %H:%M:%S')
                            days_old = (datetime.now() - update_time).days
                            if days_old > 3:  # 空列表缓存超过3天，重新获取
                                return None
                        except:
                            pass
                        return []
                    # 如果sectors字段有值，返回解析后的列表
                    return sectors_str.split(',') if sectors_str else []

        except Exception as e:
            print(f"读取板块缓存失败: {e}")

        # 缓存中没有数据，返回None
        return None
    
    def save_stock_sectors(self, stock_code: str, sectors: List[str]):
        """
        保存股票板块到缓存
        Args:
            stock_code: 股票代码
            sectors: 板块列表（空列表也会保存，用于标记该股票确实没有板块信息）
        """
        # 使用数据库锁防止并发写入
        with self._db_locks['sectors']:
            try:
                stock_code = str(stock_code).zfill(6)
                update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                sectors_str = ','.join(sectors) if sectors else ''  # 空列表保存为空字符串

                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # 插入或更新数据
                    cursor.execute('''
                        INSERT OR REPLACE INTO stock_sectors
                        (code, sectors, update_time)
                        VALUES (?, ?, ?)
                    ''', (stock_code, sectors_str, update_time))

                    conn.commit()

            except Exception as e:
                print(f"保存板块缓存失败: {e}")
                import traceback
                traceback.print_exc()
    
    def get_stock_concepts(self, stock_code: str, force_refresh: bool = False) -> Optional[List[str]]:
        """
        从缓存获取股票概念
        Args:
            stock_code: 股票代码
            force_refresh: 是否强制刷新
        Returns:
            概念列表，如果缓存中没有数据返回None，如果缓存中保存了空列表返回[]
        """
        if force_refresh:
            return None

        stock_code = str(stock_code).zfill(6)

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 查询概念数据
                cursor.execute('''
                    SELECT concepts, update_time FROM stock_concepts
                    WHERE code = ? AND update_time >= datetime('now', '-7 day')
                ''', (stock_code,))

                result = cursor.fetchone()
                if result:
                    concepts_str, update_time_str = result

                    # 如果concepts字段存在但为空字符串，说明之前保存了空列表
                    if concepts_str == '':
                        # 检查缓存时间，如果超过3天，返回None让fetcher重新获取
                        try:
                            update_time = datetime.strptime(update_time_str, '%Y-%m-%d %H:%M:%S')
                            days_old = (datetime.now() - update_time).days
                            if days_old > 3:  # 空列表缓存超过3天，重新获取
                                return None
                        except:
                            pass
                        return []
                    # 如果concepts字段有值，返回解析后的列表
                    return concepts_str.split(',') if concepts_str else []

        except Exception as e:
            print(f"读取概念缓存失败: {e}")

        # 缓存中没有数据，返回None
        return None
    
    def save_stock_concepts(self, stock_code: str, concepts: List[str]):
        """
        保存股票概念到缓存
        Args:
            stock_code: 股票代码
            concepts: 概念列表（空列表也会保存，用于标记该股票确实没有概念信息）
        """
        # 使用数据库锁防止并发写入
        with self._db_locks['concepts']:
            try:
                stock_code = str(stock_code).zfill(6)
                update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                concepts_str = ','.join(concepts) if concepts else ''  # 空列表保存为空字符串

                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # 插入或更新数据
                    cursor.execute('''
                        INSERT OR REPLACE INTO stock_concepts
                        (code, concepts, update_time)
                        VALUES (?, ?, ?)
                    ''', (stock_code, concepts_str, update_time))

                    conn.commit()

            except Exception as e:
                print(f"保存概念缓存失败: {e}")
                import traceback
                traceback.print_exc()
    
    def get_stock_list(self, force_refresh: bool = False) -> Optional[pd.DataFrame]:
        """
        从缓存获取股票列表
        Args:
            force_refresh: 是否强制刷新
        Returns:
            股票列表DataFrame
        """
        if force_refresh:
            return None

        try:
            with sqlite3.connect(self.db_path) as conn:
                # 查询有效的股票列表（未过期）
                df = pd.read_sql_query('''
                    SELECT * FROM stock_list
                    WHERE update_time >= datetime('now', '-1 day')
                ''', conn)

                if not df.empty:
                    # 确保代码是字符串类型，并格式化为6位（补零）
                    if 'code' in df.columns:
                        df['code'] = df['code'].astype(str).str.zfill(6)
                    return df

        except Exception as e:
            print(f"读取股票列表缓存失败: {e}")

        return None

    def save_stock_list(self, stock_list: pd.DataFrame):
        """
        保存股票列表到缓存
        Args:
            stock_list: 股票列表DataFrame
        """
        try:
            # 确保代码是字符串类型，并格式化为6位（补零）
            stock_list = stock_list.copy()
            if 'code' in stock_list.columns:
                stock_list['code'] = stock_list['code'].astype(str).str.zfill(6)

            update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 清空现有数据
                cursor.execute('DELETE FROM stock_list')

                # 准备插入数据
                data_to_insert = []
                for _, row in stock_list.iterrows():
                    data_to_insert.append((
                        row.get('code'),
                        row.get('name'),
                        row.get('market'),
                        row.get('area'),
                        row.get('industry'),
                        row.get('list_date'),
                        update_time
                    ))

                # 批量插入
                cursor.executemany('''
                    INSERT INTO stock_list
                    (code, name, market, area, industry, list_date, update_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', data_to_insert)

                conn.commit()

        except Exception as e:
            print(f"保存股票列表缓存失败: {e}")
    
    def get_kline(self, symbol: str, cache_type: str = 'stock',
                  period: str = 'daily', force_refresh: bool = False) -> Optional[pd.DataFrame]:
        """
        从缓存获取K线数据（智能检查最新交易日数据）
        Args:
            symbol: 股票代码/板块名称/概念名称
            cache_type: 缓存类型 ('stock', 'sector', 'concept')
            period: 周期 ('daily', 'weekly', 'monthly')
            force_refresh: 是否强制刷新
        Returns:
            K线数据DataFrame
        """
        if force_refresh:
            return None

        try:
            with sqlite3.connect(self.db_path) as conn:
                # 查询K线数据
                df = pd.read_sql_query('''
                    SELECT symbol, date, open, high, low, close, volume, amount
                    FROM kline_data
                    WHERE symbol = ? AND cache_type = ? AND period = ?
                    AND update_time >= datetime('now', '-1 day')
                    ORDER BY date
                ''', conn, params=(symbol, cache_type, period))

                if not df.empty:
                    # 确保date列是datetime类型
                    if 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                        # 检查最新交易日数据是否存在
                        latest_date = df['date'].max()
                        today = datetime.now().date()
                        # 如果最新数据是今天或昨天（考虑交易日），则可以使用缓存
                        if isinstance(latest_date, pd.Timestamp):
                            latest_date_date = latest_date.date()
                        else:
                            latest_date_date = latest_date.date() if hasattr(latest_date, 'date') else latest_date

                        if latest_date_date >= today - timedelta(days=1):
                            return df

        except Exception as e:
            print(f"读取K线缓存失败 ({symbol}): {e}")

        return None
    
    def has_latest_trading_day_data(self, symbol: str, cache_type: str = 'stock',
                                    period: str = 'daily') -> bool:
        """
        检查是否有最新交易日的数据（用于智能跳过下载）
        Args:
            symbol: 股票代码/板块名称/概念名称
            cache_type: 缓存类型 ('stock', 'sector', 'concept')
            period: 周期 ('daily', 'weekly', 'monthly')
        Returns:
            是否有最新交易日数据
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 查询最新的数据日期
                cursor.execute('''
                    SELECT MAX(date) FROM kline_data
                    WHERE symbol = ? AND cache_type = ? AND period = ?
                    AND update_time >= datetime('now', '-1 day')
                ''', (symbol, cache_type, period))

                result = cursor.fetchone()
                if not result or not result[0]:
                    return False

                latest_date_str = result[0]
                latest_date = datetime.strptime(latest_date_str, '%Y-%m-%d').date()
                today = datetime.now().date()
                current_time = datetime.now().time()
                weekday = datetime.now().weekday()

                # 判断是否应该使用昨天的数据
                # 如果当前在交易时间内，使用昨天的数据（今天数据不完整）
                use_yesterday = False
                if weekday >= 5:  # 周末
                    use_yesterday = True
                elif current_time < datetime.strptime('09:30', '%H:%M').time():  # 还没开盘
                    use_yesterday = True
                elif (datetime.strptime('09:30', '%H:%M').time() <= current_time <= datetime.strptime('11:30', '%H:%M').time()) or \
                     (datetime.strptime('13:00', '%H:%M').time() <= current_time <= datetime.strptime('15:00', '%H:%M').time()):  # 交易中
                    use_yesterday = True
                elif datetime.strptime('11:30', '%H:%M').time() < current_time < datetime.strptime('13:00', '%H:%M').time():  # 午休
                    use_yesterday = True

                # 如果应该使用昨天的数据，检查是否有昨天的数据
                if use_yesterday:
                    # 需要昨天或更早的完整数据
                    yesterday = today - timedelta(days=1)
                    # 确保不是周末
                    while yesterday.weekday() >= 5:
                        yesterday = yesterday - timedelta(days=1)
                    return latest_date >= yesterday
                else:
                    # 可以使用今天的数据（收盘后）
                    return latest_date >= today - timedelta(days=1)

        except Exception as e:
            print(f"检查K线数据有效性失败 ({symbol}): {e}")
            return False
    
    def save_kline(self, symbol: str, data: pd.DataFrame,
                   cache_type: str = 'stock', period: str = 'daily',
                   incremental: bool = True):
        """
        保存K线数据到缓存（支持增量更新和自动清理）
        Args:
            symbol: 股票代码/板块名称/概念名称
            data: K线数据DataFrame
            cache_type: 缓存类型 ('stock', 'sector', 'concept')
            period: 周期 ('daily', 'weekly', 'monthly')
            incremental: 是否增量更新（默认True，会合并现有缓存数据）
        """
        try:
            if data is None or data.empty:
                return

            # 准备数据
            data_to_save = data.copy()

            # 确保date列存在并转换为日期字符串格式
            if 'date' in data_to_save.columns:
                data_to_save['date'] = pd.to_datetime(data_to_save['date']).dt.strftime('%Y-%m-%d')
            elif '日期' in data_to_save.columns:
                data_to_save['date'] = pd.to_datetime(data_to_save['日期']).dt.strftime('%Y-%m-%d')
                # 重命名列
                data_to_save = data_to_save.rename(columns={'日期': 'date'})

            update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 如果不是增量更新，先删除现有数据
                if not incremental:
                    cursor.execute('''
                        DELETE FROM kline_data
                        WHERE symbol = ? AND cache_type = ? AND period = ?
                    ''', (symbol, cache_type, period))

                # 准备插入数据
                data_to_insert = []
                for _, row in data_to_save.iterrows():
                    data_to_insert.append((
                        symbol,
                        cache_type,
                        period,
                        row.get('date'),
                        row.get('open'),
                        row.get('high'),
                        row.get('low'),
                        row.get('close'),
                        row.get('volume'),
                        row.get('amount'),
                        update_time
                    ))

                # 批量插入（INSERT OR REPLACE处理重复数据）
                cursor.executemany('''
                    INSERT OR REPLACE INTO kline_data
                    (symbol, cache_type, period, date, open, high, low, close, volume, amount, update_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', data_to_insert)

                # 数据清理：只保留最近N天的数据
                retention_days = getattr(config, 'KLINE_CACHE_RETENTION_DAYS', 250)
                cursor.execute('''
                    DELETE FROM kline_data
                    WHERE symbol = ? AND cache_type = ? AND period = ?
                    AND date < datetime('now', '-{} days')
                '''.format(retention_days), (symbol, cache_type, period))

                conn.commit()

        except Exception as e:
            print(f"保存K线缓存失败 ({symbol}): {e}")
    
    
    def check_cache_completeness(self, stock_codes: List[str], 
                                data_types: List[str] = None) -> Dict[str, Dict]:
        """
        检查缓存完整性，判断是否需要预加载
        Args:
            stock_codes: 股票代码列表
            data_types: 要检查的数据类型列表，如 ['fundamental', 'financial']，None表示检查所有
        Returns:
            缓存完整性统计字典，包含每个类型的覆盖率
        """
        if data_types is None:
            data_types = ['fundamental', 'financial']
        
        if not stock_codes:
            return {dt: {'total': 0, 'cached': 0, 'coverage': 0.0, 'needs_preload': False} for dt in data_types}
        
        # 抽样检查（最多检查前1000只，避免太慢）
        sample_size = min(1000, len(stock_codes))
        sample_codes = stock_codes[:sample_size]
        
        completeness = {}
        for data_type in data_types:
            cached_count = 0
            for code in sample_codes:
                if data_type == 'fundamental':
                    if self.get_fundamental(code, force_refresh=False) is not None:
                        cached_count += 1
                elif data_type == 'financial':
                    if self.get_financial(code, force_refresh=False) is not None:
                        cached_count += 1
            
            coverage = cached_count / sample_size if sample_size > 0 else 0.0
            completeness[data_type] = {
                'total': sample_size,
                'cached': cached_count,
                'coverage': coverage,
                'needs_preload': coverage < 0.5  # 覆盖率低于50%需要预加载
            }
        
        return completeness
    
    def clear_cache(self, cache_type: str = None):
        """
        清除缓存
        Args:
            cache_type: 缓存类型，None表示清除所有
                       'kline': 清除K线缓存
                       'fundamental': 清除基本面缓存
                       'financial': 清除财务缓存
                       'sectors': 清除板块缓存
                       'concepts': 清除概念缓存
                       'stock_list': 清除股票列表缓存
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                if cache_type is None:
                    # 清除所有缓存
                    cursor.execute('DELETE FROM fundamental_data')
                    cursor.execute('DELETE FROM financial_data')
                    cursor.execute('DELETE FROM stock_sectors')
                    cursor.execute('DELETE FROM stock_concepts')
                    cursor.execute('DELETE FROM stock_list')
                    cursor.execute('DELETE FROM kline_data')
                    print("已清除所有缓存")

                elif cache_type == 'kline':
                    cursor.execute('DELETE FROM kline_data')
                    print("已清除K线缓存")

                elif cache_type == 'fundamental':
                    cursor.execute('DELETE FROM fundamental_data')
                    print("已清除基本面缓存")

                elif cache_type == 'financial':
                    cursor.execute('DELETE FROM financial_data')
                    print("已清除财务缓存")

                elif cache_type == 'sectors':
                    cursor.execute('DELETE FROM stock_sectors')
                    print("已清除板块缓存")

                elif cache_type == 'concepts':
                    cursor.execute('DELETE FROM stock_concepts')
                    print("已清除概念缓存")

                elif cache_type == 'stock_list':
                    cursor.execute('DELETE FROM stock_list')
                    print("已清除股票列表缓存")

                elif cache_type == 'trade_calendar':
                    cursor.execute('DELETE FROM trade_calendar')
                    print("已清除交易日历缓存")

                else:
                    print(f"未知的缓存类型: {cache_type}")
                    return

                conn.commit()

                # 清除内存缓存
                if cache_type is None or cache_type == 'fundamental':
                    with self._fundamental_cache_lock:
                        self._fundamental_cache_memory = None
                if cache_type is None or cache_type == 'financial':
                    with self._financial_cache_lock:
                        self._financial_cache_memory = None

        except Exception as e:
            print(f"清除缓存失败: {e}")
    
    def get_trade_calendar(self, force_refresh: bool = False) -> Optional[pd.DataFrame]:
        """
        从缓存获取交易日历
        Args:
            force_refresh: 是否强制刷新
        Returns:
            交易日历DataFrame，包含 cal_date 和 is_open 列
        """
        if force_refresh:
            return None
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 查询有效的交易日历（未过期，7天内）
                df = pd.read_sql_query('''
                    SELECT cal_date, is_open FROM trade_calendar
                    WHERE update_time >= datetime('now', '-7 day')
                    ORDER BY cal_date
                ''', conn)
                
                if not df.empty:
                    return df
                
        except Exception as e:
            print(f"读取交易日历缓存失败: {e}")
        
        # 缓存中没有数据，返回None
        return None
    
    def save_trade_calendar(self, trade_cal: pd.DataFrame):
        """
        保存交易日历到缓存
        Args:
            trade_cal: 交易日历DataFrame，必须包含 cal_date 和 is_open 列
        """
        if trade_cal is None or trade_cal.empty:
            return
        
        try:
            update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 批量插入或更新数据
                data_to_insert = []
                for _, row in trade_cal.iterrows():
                    cal_date = str(row['cal_date'])
                    is_open = int(row['is_open']) if pd.notna(row['is_open']) else 0
                    data_to_insert.append((cal_date, is_open, update_time))
                
                # 使用 INSERT OR REPLACE 更新现有数据
                cursor.executemany('''
                    INSERT OR REPLACE INTO trade_calendar
                    (cal_date, is_open, update_time)
                    VALUES (?, ?, ?)
                ''', data_to_insert)
                
                conn.commit()
                
        except Exception as e:
            print(f"保存交易日历缓存失败: {e}")
            import traceback
            traceback.print_exc()
    
    def is_trading_day(self, date_str: str) -> Optional[bool]:
        """
        检查指定日期是否为交易日
        Args:
            date_str: 日期字符串，格式：YYYYMMDD 或 YYYY-MM-DD
        Returns:
            如果是交易日返回True，如果不是返回False，如果缓存中没有该日期返回None
        """
        # 标准化日期格式为 YYYYMMDD
        date_str = date_str.replace('-', '')
        if len(date_str) != 8:
            return None
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT is_open FROM trade_calendar
                    WHERE cal_date = ?
                ''', (date_str,))
                
                result = cursor.fetchone()
                if result:
                    return bool(result[0])
                
        except Exception as e:
            print(f"查询交易日历失败: {e}")
        
        return None

