"""
数据获取模块：使用tushare获取股票相关数据，集成缓存机制
"""
import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
import time
import threading
from typing import Dict, List, Optional
from .cache_manager import CacheManager
import config
import os


def is_trading_time() -> bool:
    """
    判断当前是否是A股交易时间
    Returns:
        是否在交易时间内
    """
    now = datetime.now()
    current_time = now.time()
    weekday = now.weekday()  # 0=Monday, 6=Sunday
    
    # 周末不交易
    if weekday >= 5:  # Saturday or Sunday
        return False
    
    # 交易时间：上午 9:30-11:30，下午 13:00-15:00
    morning_start = datetime.strptime('09:30', '%H:%M').time()
    morning_end = datetime.strptime('11:30', '%H:%M').time()
    afternoon_start = datetime.strptime('13:00', '%H:%M').time()
    afternoon_end = datetime.strptime('15:00', '%H:%M').time()
    
    return (morning_start <= current_time <= morning_end) or \
           (afternoon_start <= current_time <= afternoon_end)


def get_analysis_date() -> datetime:
    """
    获取用于分析的数据日期
    - 如果当前在交易时间内，使用昨天的数据（今天数据不完整）
    - 如果当前不在交易时间，使用最近一个交易日的数据
    - 如果已经收盘（15:00之后），使用今天的数据
    Returns:
        用于分析的日期
    """
    now = datetime.now()
    current_time = now.time()
    weekday = now.weekday()
    
    # 如果当前在交易时间内，使用昨天的数据（今天数据不完整）
    if is_trading_time():
        # 使用昨天的日期
        analysis_date = now - timedelta(days=1)
        # 如果昨天是周末，继续往前推
        while analysis_date.weekday() >= 5:
            analysis_date = analysis_date - timedelta(days=1)
        return analysis_date
    
    # 如果当前不在交易时间
    # 如果是周末，使用周五的数据
    if weekday >= 5:
        days_back = weekday - 4  # Saturday=1, Sunday=2
        analysis_date = now - timedelta(days=days_back)
    # 如果是工作日但不在交易时间
    else:
        # 如果已经过了15:00，可以使用今天的数据（收盘后）
        if current_time >= datetime.strptime('15:00', '%H:%M').time():
            analysis_date = now
        # 如果还没到9:30，使用昨天的数据
        elif current_time < datetime.strptime('09:30', '%H:%M').time():
            analysis_date = now - timedelta(days=1)
            # 如果昨天是周末，继续往前推
            while analysis_date.weekday() >= 5:
                analysis_date = analysis_date - timedelta(days=1)
        # 其他情况（午休时间11:30-13:00），使用昨天的数据
        else:
            analysis_date = now - timedelta(days=1)
            while analysis_date.weekday() >= 5:
                analysis_date = analysis_date - timedelta(days=1)
    
    return analysis_date


def should_use_yesterday_data() -> bool:
    """
    判断是否应该使用昨天的数据进行分析
    - 如果今天还在交易中，使用昨天的完整数据
    - 如果今天还没开盘，使用昨天的数据
    - 如果已经收盘（15:00之后），使用今天的数据
    Returns:
        是否应该使用昨天的数据
    """
    now = datetime.now()
    current_time = now.time()
    weekday = now.weekday()
    
    # 周末使用最近一个交易日的数据（昨天的）
    if weekday >= 5:
        return True
    
    # 如果已经过了15:00，可以使用今天的数据（收盘后）
    if current_time >= datetime.strptime('15:00', '%H:%M').time():
        return False
    
    # 如果当前在交易时间内，使用昨天的数据（今天数据不完整）
    if is_trading_time():
        return True
    
    # 如果还没到9:30，使用昨天的数据
    if current_time < datetime.strptime('09:30', '%H:%M').time():
        return True
    
    # 其他情况（午休时间11:30-13:00等），使用昨天的数据
    return True


def filter_stocks_by_board(stock_list: pd.DataFrame, board_types: List[str]) -> pd.DataFrame:
    """
    根据板块类型筛选股票
    Args:
        stock_list: 股票列表DataFrame，包含'code'列
        board_types: 板块类型列表，如 ['main', 'gem']
    Returns:
        筛选后的股票列表DataFrame
    """
    if stock_list is None or stock_list.empty:
        return pd.DataFrame()
    
    if not board_types:
        return stock_list
    
    # 将代码列转换为字符串，并格式化为6位（补零）
    stock_list = stock_list.copy()
    stock_list['code'] = stock_list['code'].astype(str).str.zfill(6)
    codes = stock_list['code']
    
    # 定义板块代码规则
    board_rules = {
        # 主板：包括上证主板(60开头)和深圳主板(00开头，但排除002中小板)
        'main': lambda code: code.startswith('60') or (code.startswith('00') and not code.startswith('002')),
        # 中小板：002xxx
        'sme': lambda code: code.startswith('002'),
        # 创业板：300xxx
        'gem': lambda code: code.startswith('300'),
        # 科创板：688xxx
        'star': lambda code: code.startswith('688'),
        # 北交所：8xxxx 或 43xxxx
        'bse': lambda code: code.startswith('8') or code.startswith('43'),
        # B股：900xxx(上证B股) 或 200xxx(深圳B股)
        'b': lambda code: code.startswith('900') or code.startswith('200'),
    }
    
    # 创建筛选条件
    mask = pd.Series([False] * len(stock_list), index=stock_list.index)
    for board_type in board_types:
        if board_type in board_rules:
            mask |= codes.apply(board_rules[board_type])
    
    return stock_list[mask].copy()


class DataFetcher:
    """数据获取类（基于tushare，集成缓存）"""
    
    def __init__(self, force_refresh: bool = False, progress_callback=None, test_sources: bool = True):
        """
        初始化数据获取器
        Args:
            force_refresh: 是否强制刷新缓存
            progress_callback: 进度回调函数，接收(status, message)参数
            test_sources: 是否测试数据源可用性（默认True）
        """
        self.force_refresh = force_refresh
        self.cache_manager = CacheManager()
        self.stock_list = None
        self.progress_callback = progress_callback
        
        # 初始化tushare
        self._init_tushare()
        
        # 请求控制参数
        self.min_request_interval = 0.2  # tushare请求间隔（秒）
        self.max_request_interval = 0.5
        self.last_request_time = 0
        self.request_count = 0
        self.batch_size = 200  # 每批处理200个请求后休息
        self.batch_rest_time = 2  # 每批休息时间（秒）
        
        # 批量模式（用于批量保存缓存，减少IO）
        self.batch_mode = False
        self.fundamental_batch = {}
        self.financial_batch = {}
        
        # 内存会话缓存
        self._spot_data_cache: Optional[pd.DataFrame] = None
        self._sector_kline_cache: Dict[str, pd.DataFrame] = {}
        self._concept_kline_cache: Dict[str, pd.DataFrame] = {}
        self._cache_lock = threading.Lock()
        self._batch_lock = threading.Lock()
        
        # 测试数据源
        if test_sources:
            try:
                self._test_tushare_connection()
            except Exception as e:
                print(f"\n错误: Tushare连接测试失败，程序无法继续运行")
                print(f"详细信息: {e}")
                print("请检查：")
                print("1. 是否已设置TUSHARE_TOKEN环境变量或在config.py中配置")
                print("2. Token是否有效")
                raise
        
        self._load_stock_list()
    
    def _init_tushare(self):
        """初始化tushare"""
        # 优先从环境变量获取token
        token = os.environ.get('TUSHARE_TOKEN')
        if not token:
            # 从config获取
            token = config.TUSHARE_TOKEN
        
        if not token:
            raise ValueError(
                "未设置Tushare Token！\n"
                "请通过以下方式之一设置：\n"
                "1. 设置环境变量: export TUSHARE_TOKEN='your_token'\n"
                "2. 在config.py中设置: TUSHARE_TOKEN = 'your_token'\n"
                "3. 在代码中设置: ts.set_token('your_token')\n"
                "获取Token请访问: https://tushare.pro/register"
            )
        
        ts.set_token(token)
        self.pro = ts.pro_api()
    
    def _test_tushare_connection(self):
        """测试tushare连接"""
        try:
            # 尝试获取交易日历，验证连接
            today = datetime.now().strftime('%Y%m%d')
            df = self.pro.trade_cal(exchange='SSE', start_date=today, end_date=today)
            if df is None or df.empty:
                raise RuntimeError("Tushare连接测试失败：无法获取数据")
        except Exception as e:
            if "权限" in str(e) or "token" in str(e).lower():
                raise RuntimeError(f"Tushare Token无效或权限不足: {e}")
            raise RuntimeError(f"Tushare连接失败: {e}")
    
    def _wait_before_request(self):
        """在请求前等待，避免请求过快被限制"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        
        if elapsed < self.min_request_interval:
            wait_time = self.min_request_interval - elapsed
            time.sleep(wait_time)
        
        self.last_request_time = time.time()
        self.request_count += 1
        
        # 每批请求后休息
        if self.request_count % self.batch_size == 0:
            time.sleep(self.batch_rest_time)
    
    def _retry_request(self, func, max_retries: int = 3, timeout: int = 30, *args, **kwargs):
        """
        带重试机制和超时保护的请求函数
        Args:
            func: 要执行的函数
            max_retries: 最大重试次数
            timeout: 超时时间（秒），默认30秒
            *args, **kwargs: 函数参数
        Returns:
            函数返回值
        """
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
        
        last_error = None
        for attempt in range(max_retries):
            try:
                self._wait_before_request()
                
                # 使用线程池实现超时控制
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(func, *args, **kwargs)
                    try:
                        result = future.result(timeout=timeout)
                        return result
                    except FutureTimeoutError:
                        raise TimeoutError(f"请求超时（{timeout}秒）")
                        
            except (TimeoutError, Exception) as e:
                last_error = e
                if attempt < max_retries - 1:
                    # 指数退避
                    wait_time = (2 ** attempt) + 0.5
                    time.sleep(wait_time)
                    continue
                else:
                    if isinstance(last_error, TimeoutError):
                        print(f"请求超时，已重试{max_retries}次，放弃该请求")
                    return None
        return None
    
    def _format_stock_code(self, stock_code: str) -> str:
        """
        格式化股票代码，tushare需要6位数字代码
        Args:
            stock_code: 股票代码（如 '000001' 或 '000001.SZ'）
        Returns:
            格式化后的股票代码（6位数字）
        """
        stock_code = str(stock_code).strip()
        
        # 移除市场后缀（如果有）
        if '.' in stock_code:
            stock_code = stock_code.split('.')[0]
        
        # 确保是6位数字
        if len(stock_code) == 6 and stock_code.isdigit():
            return stock_code
        else:
            # 尝试提取数字部分
            import re
            digits = re.findall(r'\d+', stock_code)
            if digits and len(digits[0]) == 6:
                return digits[0]
        
        return stock_code
    
    def _load_stock_list(self):
        """加载A股股票列表（带缓存）"""
        try:
            if self.progress_callback:
                self.progress_callback('loading', "正在加载股票列表...")
            
            # 先尝试从缓存读取
            cached_list = self.cache_manager.get_stock_list(self.force_refresh)
            if cached_list is not None and not cached_list.empty:
                self.stock_list = cached_list
                msg = f"从缓存加载 {len(self.stock_list)} 只股票"
                if self.progress_callback:
                    self.progress_callback('success', msg)
                else:
                    print(msg)
                return
            
            # 从网络获取
            if self.progress_callback:
                self.progress_callback('loading', "从网络获取股票列表...")
            
            def fetch_stock_list():
                # 获取股票基本信息
                df = self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')
                if df is not None and not df.empty:
                    # 重命名列以保持兼容性
                    df.rename(columns={'symbol': 'code', 'name': 'name'}, inplace=True)
                    # 只保留A股（排除B股等）
                    df = df[df['code'].str.len() == 6]
                    df = df[df['code'].str.match(r'^\d{6}$')]
                    # 确保代码是字符串类型，并格式化为6位（补零）
                    df['code'] = df['code'].astype(str).str.zfill(6)
                    return df[['code', 'name']]
                return None
            
            self.stock_list = self._retry_request(fetch_stock_list, max_retries=3, timeout=30)
            
            if self.stock_list is not None and not self.stock_list.empty:
                self.cache_manager.save_stock_list(self.stock_list)
                msg = f"成功加载 {len(self.stock_list)} 只股票"
                if self.progress_callback:
                    self.progress_callback('success', msg)
                else:
                    print(msg)
        except Exception as e:
            error_msg = f"加载股票列表失败: {e}"
            if self.progress_callback:
                self.progress_callback('failed', error_msg)
            else:
                print(error_msg)
            self.stock_list = pd.DataFrame()
    
    def get_stock_kline(self, stock_code: str, period: str = "daily", 
                       start_date: str = None, end_date: str = None) -> Optional[pd.DataFrame]:
        """
        获取股票K线数据（支持缓存检查）
        period: daily, weekly, monthly
        """
        try:
            stock_code = str(stock_code)
            clean_code = self._format_stock_code(stock_code)
            
            # 确定是否应该使用昨天的数据
            use_yesterday = should_use_yesterday_data()
            analysis_date = get_analysis_date()
            
            # 智能检查：如果最新交易日数据已存在，直接返回
            if not self.force_refresh and self.cache_manager.has_latest_trading_day_data(clean_code, 'stock', period):
                cached_kline = self.cache_manager.get_kline(clean_code, 'stock', period, False)
                if cached_kline is not None and not cached_kline.empty:
                    if use_yesterday and 'date' in cached_kline.columns:
                        cached_kline['date'] = pd.to_datetime(cached_kline['date'])
                        today = datetime.now().date()
                        cached_kline = cached_kline[cached_kline['date'].dt.date < today]
                        if not cached_kline.empty:
                            if self.progress_callback:
                                self.progress_callback('cached', f"{clean_code}: 使用缓存数据（已过滤今日不完整数据）")
                            return cached_kline
                    else:
                        if self.progress_callback:
                            self.progress_callback('cached', f"{clean_code}: 最新交易日数据已存在，跳过下载")
                        return cached_kline
            
            # 检查其他缓存，用于增量更新
            cached_kline = self.cache_manager.get_kline(clean_code, 'stock', period, self.force_refresh)
            cached_latest_date = None
            if cached_kline is not None and not cached_kline.empty and not self.force_refresh:
                if self.progress_callback:
                    self.progress_callback('cached', f"{clean_code}: K线数据已缓存（非最新）")
                # 获取缓存中的最新日期，用于增量更新
                if 'date' in cached_kline.columns:
                    cached_kline['date'] = pd.to_datetime(cached_kline['date'])
                    cached_latest_date = cached_kline['date'].max()
            
            # 准备日期参数（支持增量更新）
            if start_date is None:
                # 如果有缓存数据，从缓存最新日期+1天开始获取（增量更新）
                if cached_latest_date is not None:
                    # 从缓存最新日期的下一天开始
                    start_date_obj = cached_latest_date + timedelta(days=1)
                    # 如果下一天是周末，跳到下一个工作日
                    while start_date_obj.weekday() >= 5:
                        start_date_obj = start_date_obj + timedelta(days=1)
                    start_date = start_date_obj.strftime('%Y%m%d')
                else:
                    # 没有缓存，获取最近120天的数据
                    start_date = (analysis_date - timedelta(days=120)).strftime('%Y%m%d')
            
            if end_date is None:
                if use_yesterday:
                    # 使用昨天的数据（交易时间内或开盘前）
                    end_date_obj = analysis_date - timedelta(days=1)
                    while end_date_obj.weekday() >= 5:
                        end_date_obj = end_date_obj - timedelta(days=1)
                    end_date = end_date_obj.strftime('%Y%m%d')
                else:
                    # 收盘后（15:00之后）可以使用今天的数据
                    end_date = analysis_date.strftime('%Y%m%d')
            
            # 如果start_date >= end_date，说明缓存已经是最新的，直接返回缓存
            if cached_latest_date is not None and start_date >= end_date:
                if self.progress_callback:
                    self.progress_callback('cached', f"{clean_code}: 缓存已是最新，无需更新")
                return cached_kline
            
            # 获取tushare代码格式（需要市场后缀）
            ts_code = self._get_ts_code(clean_code)
            if not ts_code:
                return None
            
            # 获取日K线数据
            def fetch_kline():
                # tushare的daily接口
                df = self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    # 重命名列以保持兼容性
                    df.rename(columns={
                        'trade_date': 'date',
                        'open': 'open',
                        'close': 'close',
                        'high': 'high',
                        'low': 'low',
                        'vol': 'volume',
                        'amount': 'turnover',
                        'pct_chg': 'pct_change',
                    }, inplace=True)
                    
                    # 转换日期格式
                    df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
                    df = df.sort_values('date')
                    
                    # 获取换手率数据（从daily_basic接口）
                    df['turnover_rate'] = 0  # 默认值
                    try:
                        # 获取每日指标数据（包含换手率）
                        basic_df = self.pro.daily_basic(ts_code=ts_code, start_date=start_date, end_date=end_date,
                                                       fields='trade_date,turnover_rate')
                        if basic_df is not None and not basic_df.empty:
                            basic_df['date'] = pd.to_datetime(basic_df['trade_date'], format='%Y%m%d')
                            # 合并换手率数据
                            df = df.merge(basic_df[['date', 'turnover_rate']], on='date', how='left', suffixes=('', '_basic'))
                            # 如果合并成功，使用basic的换手率，否则保持原值
                            if 'turnover_rate_basic' in df.columns:
                                df['turnover_rate'] = df['turnover_rate_basic'].fillna(0)
                                df.drop(columns=['turnover_rate_basic'], inplace=True)
                    except Exception as e:
                        # 如果获取换手率失败，使用默认值0
                        pass  # 静默失败，使用默认值0
                    
                    # 确保必要的列存在
                    required_columns = ['date', 'open', 'close', 'high', 'low', 'volume']
                    for col in required_columns:
                        if col not in df.columns:
                            df[col] = 0
                    
                    return df[['date', 'open', 'close', 'high', 'low', 'volume', 'turnover', 'pct_change', 'turnover_rate']]
                return None
            
            kline = self._retry_request(fetch_kline, max_retries=3, timeout=30)
            
            if kline is None or kline.empty:
                # 如果重试后仍然失败，尝试从缓存读取
                cached_kline = self.cache_manager.get_kline(clean_code, 'stock', period, False)
                if cached_kline is not None and not cached_kline.empty:
                    if self.progress_callback:
                        self.progress_callback('cached', f"{clean_code}: 使用缓存K线数据（网络获取失败）")
                    return cached_kline
                return None
            
            # 如果应该使用昨天的数据，过滤掉今天的数据
            if use_yesterday and 'date' in kline.columns:
                today = datetime.now().date()
                original_count = len(kline)
                kline = kline[kline['date'].dt.date < today]
                if len(kline) < original_count:
                    if self.progress_callback:
                        self.progress_callback('info', f"{clean_code}: 已过滤今日不完整数据（{original_count} -> {len(kline)}条）")
            
            # 增量更新：合并缓存数据和新获取的数据
            if cached_kline is not None and not cached_kline.empty and not kline.empty:
                # 合并新旧数据
                if 'date' in kline.columns and 'date' in cached_kline.columns:
                    kline['date'] = pd.to_datetime(kline['date'])
                    cached_kline['date'] = pd.to_datetime(cached_kline['date'])
                    # 合并：保留旧数据，追加新数据
                    combined_kline = pd.concat([cached_kline, kline], ignore_index=True)
                    # 按日期排序并去重（保留最新的）
                    combined_kline = combined_kline.sort_values('date').drop_duplicates(subset=['date'], keep='last')
                    kline = combined_kline
                    if self.progress_callback:
                        self.progress_callback('info', f"{clean_code}: 增量更新完成（新增{len(kline) - len(cached_kline)}条数据）")
            
            # 保存到缓存（使用增量更新模式）
            self.cache_manager.save_kline(clean_code, kline, 'stock', period, incremental=True)
            
            return kline
        except Exception as e:
            error_msg = f"获取 {stock_code} K线数据失败: {e}"
            if self.progress_callback:
                self.progress_callback('failed', error_msg)
            else:
                print(error_msg)
        return None
    
    def _get_ts_code(self, stock_code: str) -> str:
        """
        获取tushare格式的股票代码（带市场后缀）
        Args:
            stock_code: 6位数字股票代码
        Returns:
            tushare格式代码，如 '000001.SZ'
        """
        stock_code = self._format_stock_code(stock_code)
        
        if stock_code.startswith(('60', '68')):  # 上海
            return f"{stock_code}.SH"
        elif stock_code.startswith(('00', '30')):  # 深圳
            return f"{stock_code}.SZ"
        elif stock_code.startswith(('43', '83', '87')):  # 北交所
            return f"{stock_code}.BJ"
        else:
            return f"{stock_code}.SZ"  # 默认深圳
    
    def get_stock_fundamental(self, stock_code: str) -> Optional[Dict]:
        """
        获取股票基本面数据（带缓存）
        """
        stock_code = str(stock_code)
        clean_code = self._format_stock_code(stock_code)
        
        # 先尝试从缓存读取
        cached_data = self.cache_manager.get_fundamental(clean_code, self.force_refresh)
        if cached_data is not None:
            cached_data.pop('code', None)
            cached_data.pop('update_time', None)
            return cached_data
        
        # 从网络获取
        try:
            ts_code = self._get_ts_code(clean_code)
            if not ts_code:
                return None
            
            def fetch_fundamental():
                # 获取每日指标（包含PE、PB等）
                today = datetime.now().strftime('%Y%m%d')
                df = self.pro.daily_basic(ts_code=ts_code, trade_date=today, fields='ts_code,trade_date,pe,pb,ps,turnover_rate')
                
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    return {
                        'pe_ratio': self._safe_float(latest.get('pe', 0)),
                        'pb_ratio': self._safe_float(latest.get('pb', 0)),
                        'ps_ratio': self._safe_float(latest.get('ps', 0)),
                        'turnover_rate': self._safe_float(latest.get('turnover_rate', 0)),
                    }
                return None
            
            result = self._retry_request(fetch_fundamental, max_retries=2, timeout=15)
            
            if result:
                # 保存到缓存
                if self.batch_mode:
                    with self._batch_lock:
                        self.fundamental_batch[clean_code] = result
                else:
                    self.cache_manager.save_fundamental(clean_code, result)
                return result
        except Exception as e:
            print(f"获取 {stock_code} 基本面数据失败: {e}")
        return None
    
    def get_stock_financial(self, stock_code: str, force_refresh: bool = None) -> Optional[Dict]:
        """
        获取股票财务数据（带缓存）
        """
        stock_code = str(stock_code)
        clean_code = self._format_stock_code(stock_code)
        
        if force_refresh is None:
            force_refresh = self.force_refresh
        
        # 先尝试从缓存读取
        cached_data = self.cache_manager.get_financial(clean_code, force_refresh)
        if cached_data is not None:
            cached_data.pop('code', None)
            cached_data.pop('update_time', None)
            return cached_data
        
        # 从网络获取
        try:
            ts_code = self._get_ts_code(clean_code)
            if not ts_code:
                return None
            
            def fetch_financial():
                # 获取财务指标数据
                # 获取最近一个报告期的数据
                end_date = datetime.now().strftime('%Y%m%d')
                start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
                
                df = self.pro.fina_indicator(ts_code=ts_code, start_date=start_date, end_date=end_date,
                                            fields='ts_code,end_date,roe,roa,netprofit_margin,current_ratio')
                
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    
                    # 获取利润表数据计算增长率
                    income_df = self.pro.income(ts_code=ts_code, start_date=start_date, end_date=end_date,
                                               fields='ts_code,end_date,revenue,n_income')
                    
                    revenue_growth = 0
                    profit_growth = 0
                    
                    if income_df is not None and not income_df.empty:
                        income_df = income_df.sort_values('end_date')
                        if len(income_df) >= 2:
                            latest_revenue = income_df.iloc[-1]['revenue']
                            prev_revenue = income_df.iloc[-2]['revenue']
                            if prev_revenue and prev_revenue != 0:
                                revenue_growth = ((latest_revenue - prev_revenue) / prev_revenue) * 100
                            
                            latest_profit = income_df.iloc[-1]['n_income']
                            prev_profit = income_df.iloc[-2]['n_income']
                            if prev_profit and prev_profit != 0:
                                profit_growth = ((latest_profit - prev_profit) / prev_profit) * 100
                    
                    return {
                        'roe': self._safe_float(latest.get('roe', 0)),
                        'roa': self._safe_float(latest.get('roa', 0)),
                        'revenue_growth': revenue_growth,
                        'profit_growth': profit_growth,
                    }
                return None
            
            result = self._retry_request(fetch_financial, max_retries=3, timeout=20)
            
            if result:
                # 保存到缓存
                if self.batch_mode:
                    with self._batch_lock:
                        self.financial_batch[clean_code] = result
                else:
                    self.cache_manager.save_financial(clean_code, result)
                return result
        except Exception as e:
            print(f"获取 {stock_code} 财务数据失败: {e}")
        return None
    
    def _safe_float(self, value) -> float:
        """安全转换为float"""
        try:
            if isinstance(value, str):
                value = value.replace(',', '').replace('--', '0').replace('-', '0')
            return float(value) if value else 0.0
        except:
            return 0.0
    
    def get_stock_sectors(self, stock_code: str, force_refresh: bool = None) -> List[str]:
        """
        获取股票所属板块（带缓存）
        """
        stock_code = str(stock_code)
        clean_code = self._format_stock_code(stock_code)
        
        if force_refresh is None:
            force_refresh = self.force_refresh
        
        # 先尝试从缓存读取
        cached_sectors = self.cache_manager.get_stock_sectors(clean_code, force_refresh)
        # 如果缓存中有数据（包括空列表），直接返回
        # None表示缓存中没有该股票的数据，需要重新获取
        if cached_sectors is not None:
            return cached_sectors
        
        # 从网络获取
        try:
            ts_code = self._get_ts_code(clean_code)
            if not ts_code:
                return []
            
            def fetch_sectors():
                # 获取股票所属行业（板块）
                df = self.pro.stock_basic(ts_code=ts_code, fields='ts_code,industry')
                if df is not None and not df.empty:
                    industry = df.iloc[0].get('industry', '')
                    if industry and industry.strip():
                        return [industry.strip()]
                return []
            
            sectors = self._retry_request(fetch_sectors, max_retries=2, timeout=10)
            if sectors:
                self.cache_manager.save_stock_sectors(clean_code, sectors)
                return sectors
        except Exception as e:
            print(f"获取 {stock_code} 板块信息失败: {e}")
        
        # 保存空列表到缓存，避免重复请求
        self.cache_manager.save_stock_sectors(clean_code, [])
        return []
    
    def get_stock_concepts(self, stock_code: str, force_refresh: bool = None) -> List[str]:
        """
        获取股票所属概念（带缓存）
        """
        stock_code = str(stock_code)
        clean_code = self._format_stock_code(stock_code)
        
        if force_refresh is None:
            force_refresh = self.force_refresh
        
        # 先尝试从缓存读取
        cached_concepts = self.cache_manager.get_stock_concepts(clean_code, force_refresh)
        # 如果缓存中有数据（包括空列表），直接返回
        # None表示缓存中没有该股票的数据，需要重新获取
        if cached_concepts is not None:
            return cached_concepts
        
        # 从网络获取
        try:
            ts_code = self._get_ts_code(clean_code)
            if not ts_code:
                return []
            
            def fetch_concepts():
                # 获取股票所属概念
                try:
                    concept_df = self.pro.concept_detail(ts_code=ts_code, fields='id,name')
                    if concept_df is not None and not concept_df.empty:
                        concepts = concept_df['name'].dropna().tolist()
                        # 过滤空字符串
                        concepts = [c.strip() for c in concepts if c and c.strip()]
                        return concepts
                except Exception as e:
                    # 可能是积分不足或其他错误
                    if self.progress_callback:
                        self.progress_callback('info', f"获取概念数据失败（可能需要2000积分）: {e}")
                return []
            
            concepts = self._retry_request(fetch_concepts, max_retries=2, timeout=15)
            if concepts:
                self.cache_manager.save_stock_concepts(clean_code, concepts)
                return concepts
        except Exception as e:
            if self.progress_callback:
                self.progress_callback('info', f"获取 {stock_code} 概念信息失败: {e}")
            else:
                print(f"获取 {stock_code} 概念信息失败: {e}")
        
        # 保存空列表到缓存，避免重复请求
        self.cache_manager.save_stock_concepts(clean_code, [])
        return []
    
    def get_sector_kline(self, sector_name: str, period: str = "daily") -> Optional[pd.DataFrame]:
        """
        获取板块K线数据（支持内存缓存和磁盘缓存）
        通过行业指数获取板块K线数据
        """
        try:
            # 检查内存缓存
            cache_key = f"{sector_name}_{period}"
            with self._cache_lock:
                if cache_key in self._sector_kline_cache:
                    return self._sector_kline_cache[cache_key].copy()
            
            # 检查磁盘缓存
            if not self.force_refresh:
                cached_kline = self.cache_manager.get_kline(sector_name, 'sector', period, False)
                if cached_kline is not None and not cached_kline.empty:
                    # 存入内存缓存
                    with self._cache_lock:
                        self._sector_kline_cache[cache_key] = cached_kline
                    return cached_kline
            
            # 通过行业指数获取板块K线数据
            def fetch_sector_kline():
                # 1. 获取行业指数列表
                index_df = self.pro.index_basic(market='SW', fields='ts_code,name')
                if index_df is None or index_df.empty:
                    return None
                
                # 2. 查找匹配的行业指数（通过名称匹配）
                # 优化匹配逻辑：先精确匹配，再模糊匹配
                matched_index = None
                sector_name_clean = sector_name.strip()
                
                # 精确匹配：板块名称完全匹配或包含在指数名称中（排除退市指数）
                for _, row in index_df.iterrows():
                    index_name = row['name']
                    # 跳过退市指数
                    if '退市' in index_name:
                        continue
                    if sector_name_clean in index_name or index_name in sector_name_clean:
                        matched_index = row['ts_code']
                        break
                
                # 如果没找到精确匹配，尝试模糊匹配
                if matched_index is None:
                    # 提取板块名称的关键词（去除常见后缀）
                    keywords = sector_name_clean.replace('行业', '').replace('板块', '').strip()
                    if len(keywords) >= 2:
                        for _, row in index_df.iterrows():
                            index_name = row['name']
                            # 跳过退市指数
                            if '退市' in index_name:
                                continue
                            # 检查关键词是否在指数名称中
                            if keywords in index_name or any(kw in index_name for kw in [keywords[:2], keywords[:3]] if len(kw) >= 2):
                                matched_index = row['ts_code']
                                break
                
                # 如果还是没找到，尝试使用行业名称的前几个字符匹配（排除退市指数）
                if matched_index is None and len(sector_name_clean) >= 2:
                    for _, row in index_df.iterrows():
                        index_name = row['name']
                        # 跳过退市指数
                        if '退市' in index_name:
                            continue
                        if sector_name_clean[:2] in index_name or sector_name_clean[:3] in index_name:
                            matched_index = row['ts_code']
                            break
                
                if matched_index is None:
                    return None
                
                # 3. 获取指数K线数据
                analysis_date = get_analysis_date()
                start_date = (analysis_date - timedelta(days=120)).strftime('%Y%m%d')
                end_date = analysis_date.strftime('%Y%m%d')
                
                kline_df = self.pro.index_daily(ts_code=matched_index, start_date=start_date, end_date=end_date)
                if kline_df is None or kline_df.empty:
                    return None
                
                # 4. 格式化数据
                kline_df.rename(columns={
                    'trade_date': 'date',
                    'open': 'open',
                    'close': 'close',
                    'high': 'high',
                    'low': 'low',
                    'vol': 'volume',
                    'amount': 'turnover',
                    'pct_chg': 'pct_change',
                }, inplace=True)
                
                kline_df['date'] = pd.to_datetime(kline_df['date'], format='%Y%m%d')
                kline_df = kline_df.sort_values('date')
                
                # 确保有收盘价列（用于评分器）
                if 'close' not in kline_df.columns and '收盘' not in kline_df.columns:
                    return None
                
                return kline_df
            
            sector_kline = self._retry_request(fetch_sector_kline, max_retries=2, timeout=20)
            
            if sector_kline is not None and not sector_kline.empty:
                # 存入内存缓存
                with self._cache_lock:
                    self._sector_kline_cache[cache_key] = sector_kline
                # 保存到磁盘缓存
                self.cache_manager.save_kline(sector_name, sector_kline, 'sector', period, incremental=True)
                return sector_kline
            
        except Exception as e:
            if self.progress_callback:
                self.progress_callback('info', f"获取板块 {sector_name} K线数据失败: {e}")
            else:
                print(f"获取板块 {sector_name} K线数据失败: {e}")
        return None
    
    def get_concept_kline(self, concept_name: str, period: str = "daily") -> Optional[pd.DataFrame]:
        """
        获取概念K线数据（支持内存缓存和磁盘缓存）
        通过概念成分股计算概念指数
        """
        try:
            # 检查内存缓存
            cache_key = f"{concept_name}_{period}"
            with self._cache_lock:
                if cache_key in self._concept_kline_cache:
                    return self._concept_kline_cache[cache_key].copy()
            
            # 检查磁盘缓存
            if not self.force_refresh:
                cached_kline = self.cache_manager.get_kline(concept_name, 'concept', period, False)
                if cached_kline is not None and not cached_kline.empty:
                    # 存入内存缓存
                    with self._cache_lock:
                        self._concept_kline_cache[cache_key] = cached_kline
                    return cached_kline
            
            # 通过概念成分股计算概念指数
            def fetch_concept_kline():
                # 1. 获取概念列表
                concept_df = self.pro.concept_detail(fields='id,name')
                if concept_df is None or concept_df.empty:
                    return None
                
                # 2. 查找匹配的概念ID
                matched_concept_id = None
                for _, row in concept_df.iterrows():
                    if concept_name in row['name'] or row['name'] in concept_name:
                        matched_concept_id = row['id']
                        break
                
                if matched_concept_id is None:
                    return None
                
                # 3. 获取概念成分股列表
                stock_df = self.pro.concept_detail(id=matched_concept_id, fields='ts_code')
                if stock_df is None or stock_df.empty:
                    return None
                
                # 3.1 获取成分股市值并按市值排序，取TOP20
                analysis_date = get_analysis_date()
                trade_date = analysis_date.strftime('%Y%m%d')
                
                # 获取所有成分股的市值数据
                stock_codes = stock_df['ts_code'].tolist()
                stock_market_cap = []
                
                for ts_code in stock_codes:
                    try:
                        # 获取股票的最新市值数据（使用daily_basic接口）
                        daily_basic = self.pro.daily_basic(ts_code=ts_code, trade_date=trade_date, fields='ts_code,total_mv')
                        if daily_basic is not None and not daily_basic.empty and 'total_mv' in daily_basic.columns:
                            market_cap = daily_basic.iloc[0]['total_mv']
                            if pd.notna(market_cap) and market_cap > 0:
                                stock_market_cap.append({'ts_code': ts_code, 'total_mv': market_cap})
                    except:
                        continue  # 跳过获取失败的股票
                
                # 如果没有获取到市值数据，尝试使用最近一个交易日的数据
                if not stock_market_cap:
                    # 获取最近5个交易日的数据
                    for ts_code in stock_codes[:50]:  # 限制最多50只，避免请求过多
                        try:
                            end_date = analysis_date.strftime('%Y%m%d')
                            start_date = (analysis_date - timedelta(days=5)).strftime('%Y%m%d')
                            daily_basic = self.pro.daily_basic(ts_code=ts_code, start_date=start_date, end_date=end_date, fields='ts_code,trade_date,total_mv')
                            if daily_basic is not None and not daily_basic.empty:
                                # 取最新的市值数据
                                latest = daily_basic.sort_values('trade_date', ascending=False).iloc[0]
                                market_cap = latest['total_mv']
                                if pd.notna(market_cap) and market_cap > 0:
                                    stock_market_cap.append({'ts_code': ts_code, 'total_mv': market_cap})
                        except:
                            continue
                
                # 按市值降序排序，取TOP20（不足20只取全部）
                if stock_market_cap:
                    stock_market_cap.sort(key=lambda x: x['total_mv'], reverse=True)
                    top_stocks = [item['ts_code'] for item in stock_market_cap[:20]]
                else:
                    # 如果获取市值失败，使用原始的前20只股票
                    top_stocks = stock_codes[:20]
                
                # 4. 获取TOP20成分股的K线数据并计算概念指数
                start_date = (analysis_date - timedelta(days=120)).strftime('%Y%m%d')
                end_date = analysis_date.strftime('%Y%m%d')
                
                concept_kline_dict = {}
                stock_codes = top_stocks  # 使用市值TOP20的股票
                
                for ts_code in stock_codes:
                    try:
                        stock_kline = self.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                        if stock_kline is not None and not stock_kline.empty:
                            for _, row in stock_kline.iterrows():
                                trade_date = row['trade_date']
                                close_price = row['close']
                                
                                if trade_date not in concept_kline_dict:
                                    concept_kline_dict[trade_date] = []
                                concept_kline_dict[trade_date].append(close_price)
                    except:
                        continue  # 跳过失败的股票
                
                if not concept_kline_dict:
                    return None
                
                # 5. 计算概念指数（等权重平均）
                concept_data = []
                for trade_date in sorted(concept_kline_dict.keys()):
                    prices = concept_kline_dict[trade_date]
                    if prices:
                        avg_price = sum(prices) / len(prices)
                        concept_data.append({
                            'date': pd.to_datetime(trade_date, format='%Y%m%d'),
                            'close': avg_price,
                            'open': avg_price,  # 简化处理
                            'high': avg_price,
                            'low': avg_price,
                            'volume': 0,
                            'turnover': 0,
                            'pct_change': 0,
                        })
                
                if not concept_data:
                    return None
                
                concept_kline = pd.DataFrame(concept_data)
                concept_kline = concept_kline.sort_values('date')
                
                return concept_kline
            
            concept_kline = self._retry_request(fetch_concept_kline, max_retries=2, timeout=30)
            
            if concept_kline is not None and not concept_kline.empty:
                # 存入内存缓存
                with self._cache_lock:
                    self._concept_kline_cache[cache_key] = concept_kline
                # 保存到磁盘缓存
                self.cache_manager.save_kline(concept_name, concept_kline, 'concept', period, incremental=True)
                return concept_kline
            
        except Exception as e:
            if self.progress_callback:
                self.progress_callback('info', f"获取概念 {concept_name} K线数据失败: {e}")
            else:
                print(f"获取概念 {concept_name} K线数据失败: {e}")
        return None
    
    def get_all_stock_codes(self, board_types: List[str] = None) -> List[str]:
        """
        获取股票代码列表
        Args:
            board_types: 板块类型列表，如 ['main', 'gem']，None表示所有板块
        Returns:
            股票代码列表
        """
        if self.stock_list is not None and not self.stock_list.empty:
            if board_types is None:
                return self.stock_list['code'].tolist()
            else:
                # 筛选板块
                filtered = filter_stocks_by_board(self.stock_list, board_types)
                return filtered['code'].tolist()
        return []
    
    def flush_batch_cache(self):
        """刷新批量缓存（将收集的数据批量保存）"""
        try:
            with self._batch_lock:
                if self.fundamental_batch:
                    batch_to_save = self.fundamental_batch.copy()
                    self.fundamental_batch.clear()
                else:
                    batch_to_save = {}
            
            if batch_to_save:
                self.cache_manager.batch_save_fundamental(batch_to_save)
            
            count = len(batch_to_save)
        except Exception as e:
            print(f"批量保存基本面缓存失败: {e}")
            count = 0
        
        try:
            with self._batch_lock:
                if self.financial_batch:
                    batch_to_save = self.financial_batch.copy()
                    self.financial_batch.clear()
                else:
                    batch_to_save = {}
            
            if batch_to_save:
                self.cache_manager.batch_save_financial(batch_to_save)
            
            count += len(batch_to_save)
        except Exception as e:
            print(f"批量保存财务缓存失败: {e}")
        
        return count
    
    def preload_stock_data(self, stock_codes: List[str], data_types: List[str] = None,
                          max_workers: int = 5, show_progress: bool = True) -> Dict[str, Dict]:
        """
        预加载股票数据（支持显示详细进度）
        Args:
            stock_codes: 股票代码列表
            data_types: 要加载的数据类型列表，如 ['kline', 'fundamental', 'financial']，None表示加载所有
            max_workers: 最大线程数
            show_progress: 是否显示进度
        Returns:
            加载结果统计字典
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from tqdm import tqdm
        
        if data_types is None:
            data_types = ['kline', 'fundamental', 'financial']
        
        # 启用批量模式
        self.batch_mode = True
        
        stats = {
            'total': len(stock_codes),
            'kline': {'success': 0, 'cached': 0, 'failed': 0},
            'fundamental': {'success': 0, 'cached': 0, 'failed': 0},
            'financial': {'success': 0, 'cached': 0, 'failed': 0},
        }
        
        import threading
        stats_lock = threading.Lock()
        processed_count = 0
        
        def load_single_stock_data(stock_code: str):
            """加载单只股票的数据"""
            nonlocal processed_count
            result = {'code': stock_code, 'kline': None, 'fundamental': None, 'financial': None}
            
            # 加载K线数据
            if 'kline' in data_types:
                try:
                    kline = self.get_stock_kline(stock_code)
                    if kline is not None and not kline.empty:
                        result['kline'] = 'success'
                        with stats_lock:
                            stats['kline']['success'] += 1
                    else:
                        result['kline'] = 'failed'
                        with stats_lock:
                            stats['kline']['failed'] += 1
                except Exception as e:
                    result['kline'] = 'failed'
                    with stats_lock:
                        stats['kline']['failed'] += 1
            
            # 加载基本面数据
            if 'fundamental' in data_types:
                try:
                    cached = self.cache_manager.get_fundamental(stock_code, self.force_refresh)
                    if cached is not None:
                        result['fundamental'] = 'cached'
                        with stats_lock:
                            stats['fundamental']['cached'] += 1
                    else:
                        fund = self.get_stock_fundamental(stock_code)
                        if fund is not None:
                            result['fundamental'] = 'success'
                            with stats_lock:
                                stats['fundamental']['success'] += 1
                        else:
                            result['fundamental'] = 'failed'
                            with stats_lock:
                                stats['fundamental']['failed'] += 1
                except Exception as e:
                    result['fundamental'] = 'failed'
                    with stats_lock:
                        stats['fundamental']['failed'] += 1
            
            # 加载财务数据
            if 'financial' in data_types:
                try:
                    cached = self.cache_manager.get_financial(stock_code, self.force_refresh)
                    if cached is not None:
                        result['financial'] = 'cached'
                        with stats_lock:
                            stats['financial']['cached'] += 1
                    else:
                        fin = self.get_stock_financial(stock_code)
                        if fin is not None:
                            result['financial'] = 'success'
                            with stats_lock:
                                stats['financial']['success'] += 1
                        else:
                            result['financial'] = 'failed'
                            with stats_lock:
                                stats['financial']['failed'] += 1
                except Exception as e:
                    result['financial'] = 'failed'
                    with stats_lock:
                        stats['financial']['failed'] += 1
            
            # 定期批量保存
            with stats_lock:
                processed_count += 1
                if processed_count % 200 == 0:
                    self.flush_batch_cache()
            
            return result
        
        if show_progress:
            print(f"\n开始预加载 {len(stock_codes)} 只股票的数据...")
            print(f"数据类型: {', '.join(data_types)}")
            print("=" * 60)
        
        # 使用线程池并行加载
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(load_single_stock_data, code): code 
                      for code in stock_codes}
            
            if show_progress:
                pbar = tqdm(total=len(stock_codes), desc="数据预加载进度",
                           bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]')
            
            for future in as_completed(futures):
                result = future.result()
                if show_progress:
                    pbar.update(1)
                    if pbar.n % 50 == 0:
                        pbar.set_postfix({
                            'K线': f"{stats['kline']['success']+stats['kline']['cached']}/{stats['total']}",
                            '基本面': f"{stats['fundamental']['success']+stats['fundamental']['cached']}/{stats['total']}",
                            '财务': f"{stats['financial']['success']+stats['financial']['cached']}/{stats['total']}"
                        })
            
            if show_progress:
                pbar.close()
        
        # 最后批量保存剩余数据
        self.flush_batch_cache()
        self.batch_mode = False
        
        if show_progress:
            print("\n" + "=" * 60)
            print("数据预加载完成！统计信息：")
            for data_type in data_types:
                type_stats = stats[data_type]
                total_loaded = type_stats['success'] + type_stats['cached']
                print(f"\n{data_type.upper()}:")
                print(f"  成功加载: {type_stats['success']} 只")
                print(f"  已缓存: {type_stats['cached']} 只")
                print(f"  失败: {type_stats['failed']} 只")
                print(f"  总计: {total_loaded}/{stats['total']} ({total_loaded/stats['total']*100:.1f}%)")
            print("=" * 60)
        
        return stats
    
    def ensure_data_ready(self, stock_codes: List[str], board_types: List[str] = None,
                        max_workers: int = 10, min_coverage: float = 0.5) -> bool:
        """
        确保数据就绪：检查缓存完整性，如果覆盖率不足则自动预加载
        """
        if not stock_codes:
            if self.stock_list is not None and not self.stock_list.empty:
                if board_types:
                    filtered = filter_stocks_by_board(self.stock_list, board_types)
                    stock_codes = filtered['code'].tolist()
                else:
                    stock_codes = self.stock_list['code'].tolist()
        
        if not stock_codes:
            print("警告: 没有找到要评估的股票")
            return False
        
        # 检查缓存完整性
        print("\n检查缓存完整性...")
        completeness = self.cache_manager.check_cache_completeness(
            stock_codes, 
            data_types=['fundamental', 'financial']
        )
        
        # 显示检查结果
        needs_preload = False
        for data_type, stats in completeness.items():
            coverage = stats['coverage']
            status = "✓" if coverage >= min_coverage else "✗"
            print(f"  {data_type}: {status} 覆盖率 {coverage*100:.1f}% ({stats['cached']}/{stats['total']})")
            
            if stats.get('needs_preload', False):
                needs_preload = True
        
        # 如果需要预加载，执行预加载
        if needs_preload:
            print(f"\n检测到缓存覆盖率不足，开始预加载数据...")
            print("=" * 60)
            
            preload_types = []
            if completeness.get('fundamental', {}).get('needs_preload', False):
                preload_types.append('fundamental')
            if completeness.get('financial', {}).get('needs_preload', False):
                preload_types.append('financial')
            
            # 执行预加载
            self.preload_stock_data(
                stock_codes=stock_codes,
                data_types=preload_types,
                max_workers=max_workers,
                show_progress=True
            )
            
            # 再次检查覆盖率
            print("\n预加载完成，重新检查缓存完整性...")
            completeness_after = self.cache_manager.check_cache_completeness(
                stock_codes,
                data_types=['fundamental', 'financial']
            )
            
            all_ready = True
            for data_type, stats in completeness_after.items():
                coverage = stats['coverage']
                status = "✓" if coverage >= min_coverage else "✗"
                print(f"  {data_type}: {status} 覆盖率 {coverage*100:.1f}% ({stats['cached']}/{stats['total']})")
                if coverage < min_coverage:
                    all_ready = False
            
            return all_ready
        else:
            print("\n缓存数据完整，无需预加载")
            return True

