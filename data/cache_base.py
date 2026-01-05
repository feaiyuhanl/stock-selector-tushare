"""
缓存管理基础模块：数据库初始化、连接管理、工具方法
"""
import pandas as pd
import os
import threading
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from .utils import normalize_stock_code


class CacheBase:
    """缓存管理基础类：提供数据库初始化、连接管理、工具方法"""
    
    def __init__(self, cache_dir: str = "cache"):
        """
        初始化缓存管理器基础功能
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
            'stock_list': 1,       # 缓存有效期1天（超过1天自动失效）
            'kline': 1,            # 缓存有效期1天（必须是今天，否则失效）
            'trade_calendar': 7,   # 交易日历缓存有效期7天（每周刷新一次）
            'index_weight': 1,     # 指数权重缓存有效期1天（每日更新）
        }

        # 定义哪些数据类型是低频的（变化频率低，但缓存失效后仍会重新获取）
        self.low_frequency_types = ['financial']

        # 数据库级别的锁，防止并发写入
        self._db_locks = {
            'fundamental': threading.Lock(),
            'financial': threading.Lock(),
            'stock_list': threading.Lock(),
            'kline': threading.Lock(),
            'index_weight': threading.Lock(),
        }
        
        # 初始化数据库连接配置（设置超时和WAL模式）
        self._init_database_connection()

        # 初始化数据库
        self._init_database()
    
    @staticmethod
    def _normalize_stock_code(stock_code: str) -> str:
        """标准化股票代码为6位字符串"""
        return normalize_stock_code(stock_code)
    
    def _init_database_connection(self):
        """初始化数据库连接配置（启用WAL模式以提高并发性能）"""
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                # 启用WAL模式（Write-Ahead Logging），提高并发性能
                conn.execute('PRAGMA journal_mode=WAL')
                conn.commit()
        except Exception as e:
            print(f"初始化数据库连接配置失败: {e}")
    
    def _get_db_connection(self, timeout=30.0):
        """
        获取数据库连接（带超时设置）
        Args:
            timeout: 超时时间（秒）
        Returns:
            数据库连接对象
        """
        return sqlite3.connect(self.db_path, timeout=timeout)
    
    def _init_database(self):
        """初始化SQLite数据库和表结构"""
        with self._get_db_connection() as conn:
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
            
            # 创建指数权重数据表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS index_weight_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    index_code TEXT NOT NULL,        -- 指数代码，如 '000300.SH'
                    trade_date TEXT NOT NULL,        -- 交易日期，格式：YYYYMMDD
                    con_code TEXT NOT NULL,          -- 成分股代码，6位数字
                    weight REAL,                     -- 权重（百分比）
                    update_time TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(index_code, trade_date, con_code)
                )
            ''')

            # 创建索引以提高查询性能
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_fundamental_code ON fundamental_data(code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_financial_code ON financial_data(code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_stock_list_code ON stock_list(code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_kline_symbol_type_period ON kline_data(symbol, cache_type, period)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_kline_date ON kline_data(date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_trade_calendar_date ON trade_calendar(cal_date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_index_weight_code_date ON index_weight_data(index_code, trade_date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_index_weight_con_code ON index_weight_data(con_code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_index_weight_date ON index_weight_data(trade_date)')

            conn.commit()

    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)
    
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
    
    def check_cache_completeness(self, stock_codes: List[str], 
                                data_types: List[str] = None,
                                fundamental_cache=None) -> Dict[str, Dict]:
        """
        检查缓存完整性，判断是否需要预加载
        Args:
            stock_codes: 股票代码列表
            data_types: 要检查的数据类型列表，如 ['fundamental', 'financial']，None表示检查所有
            fundamental_cache: FundamentalCache实例，用于获取缓存数据
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
                    if fundamental_cache and fundamental_cache.get_fundamental(code, force_refresh=False) is not None:
                        cached_count += 1
                elif data_type == 'financial':
                    if fundamental_cache and fundamental_cache.get_financial(code, force_refresh=False) is not None:
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
                       'stock_list': 清除股票列表缓存
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                if cache_type is None:
                    # 清除所有缓存
                    cursor.execute('DELETE FROM fundamental_data')
                    cursor.execute('DELETE FROM financial_data')
                    cursor.execute('DELETE FROM stock_list')
                    cursor.execute('DELETE FROM kline_data')
                    cursor.execute('DELETE FROM index_weight_data')
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

                elif cache_type == 'stock_list':
                    cursor.execute('DELETE FROM stock_list')
                    print("已清除股票列表缓存")

                elif cache_type == 'trade_calendar':
                    cursor.execute('DELETE FROM trade_calendar')
                    print("已清除交易日历缓存")

                elif cache_type == 'index_weight':
                    cursor.execute('DELETE FROM index_weight_data')
                    print("已清除指数权重缓存")

                else:
                    print(f"未知的缓存类型: {cache_type}")
                    return

                conn.commit()

                # 清除内存缓存（如果存在）
                if hasattr(self, '_fundamental_cache_memory'):
                    if cache_type is None or cache_type == 'fundamental':
                        if hasattr(self, '_fundamental_cache_lock'):
                            with self._fundamental_cache_lock:
                                self._fundamental_cache_memory = None
                if hasattr(self, '_financial_cache_memory'):
                    if cache_type is None or cache_type == 'financial':
                        if hasattr(self, '_financial_cache_lock'):
                            with self._financial_cache_lock:
                                self._financial_cache_memory = None

        except Exception as e:
            print(f"清除缓存失败: {e}")
    
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
                        df['code'] = df['code'].apply(self._normalize_stock_code)
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
                stock_list['code'] = stock_list['code'].apply(self._normalize_stock_code)

            update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            with self._db_locks['stock_list']:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # 先清空旧数据
                    cursor.execute('DELETE FROM stock_list')

                    # 批量插入新数据
                    data_to_insert = []
                    for _, row in stock_list.iterrows():
                        data_to_insert.append((
                            str(row['code']),
                            str(row.get('name', '')),
                            str(row.get('market', '')),
                            str(row.get('area', '')),
                            str(row.get('industry', '')),
                            str(row.get('list_date', '')),
                            update_time
                        ))

                    cursor.executemany('''
                        INSERT INTO stock_list
                        (code, name, market, area, industry, list_date, update_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', data_to_insert)

                    conn.commit()

        except Exception as e:
            print(f"保存股票列表缓存失败: {e}")
            import traceback
            traceback.print_exc()
    
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

