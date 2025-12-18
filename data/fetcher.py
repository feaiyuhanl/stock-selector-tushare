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
        self.sector_kline_batch = {}  # 批量保存板块K线缓存
        
        # 内存会话缓存
        self._spot_data_cache: Optional[pd.DataFrame] = None
        self._sector_kline_cache: Dict[str, pd.DataFrame] = {}
        self._concept_kline_cache: Dict[str, pd.DataFrame] = {}
        self._cache_lock = threading.Lock()
        self._batch_lock = threading.Lock()
        
        # 行业分类映射表（使用 index_classify + index_member）
        # {stock_code: [industry_name1, industry_name2, ...]}
        self._stock_industry_map: Dict[str, List[str]] = {}
        # {industry_name: index_code}
        self._industry_index_map: Dict[str, str] = {}
        self._industry_map_loaded = False
        self._industry_map_lock = threading.Lock()
        
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
        
        # 优化：延迟加载股票列表，只在真正需要时加载（如调用get_all_stock_codes时）
        # self._load_stock_list()  # 已移除立即加载
    
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
    
    def _load_industry_mapping(self):
        """
        加载行业分类映射表（使用 index_classify + index_member）
        建立股票到行业的映射表和行业到指数代码的映射表
        """
        with self._industry_map_lock:
            if self._industry_map_loaded:
                return
            
            try:
                if self.progress_callback:
                    self.progress_callback('loading', "正在加载行业分类映射表...")
                
                # 1. 获取申万一级行业分类
                industries_df = self.pro.index_classify(level='L1', src='SW2021')
                if industries_df is None or industries_df.empty:
                    if self.progress_callback:
                        self.progress_callback('warning', "无法获取行业分类数据")
                    return
                
                # 2. 建立行业名称到指数代码的映射
                for _, industry in industries_df.iterrows():
                    industry_name = industry.get('industry_name', '').strip()
                    index_code = industry.get('index_code', '').strip()
                    if industry_name and index_code:
                        self._industry_index_map[industry_name] = index_code
                
                # 3. 批量获取每个行业的成分股，建立股票到行业的映射
                total_industries = len(industries_df)
                for idx, (_, industry) in enumerate(industries_df.iterrows(), 1):
                    index_code = industry.get('index_code', '').strip()
                    industry_name = industry.get('industry_name', '').strip()
                    
                    if not index_code or not industry_name:
                        continue
                    
                    try:
                        # 获取该行业的成分股
                        members_df = self.pro.index_member(index_code=index_code)
                        if members_df is not None and not members_df.empty:
                            for _, member in members_df.iterrows():
                                stock_code = member.get('con_code', '').strip()
                                if stock_code:
                                    # 转换为标准格式（6位数字）
                                    clean_code = self._format_stock_code(stock_code)
                                    if clean_code and len(clean_code) == 6:
                                        if clean_code not in self._stock_industry_map:
                                            self._stock_industry_map[clean_code] = []
                                        if industry_name not in self._stock_industry_map[clean_code]:
                                            self._stock_industry_map[clean_code].append(industry_name)
                        
                        # 控制请求频率
                        if idx % 10 == 0:
                            import time
                            time.sleep(0.3)
                    except Exception as e:
                        if self.progress_callback:
                            self.progress_callback('warning', f"获取行业 {industry_name} 成分股失败: {e}")
                        continue
                
                self._industry_map_loaded = True
                msg = f"已加载 {len(self._industry_index_map)} 个行业分类，覆盖 {len(self._stock_industry_map)} 只股票"
                if self.progress_callback:
                    self.progress_callback('success', msg)
                else:
                    print(msg)
                    
            except Exception as e:
                if self.progress_callback:
                    self.progress_callback('error', f"加载行业分类映射表失败: {e}")
                else:
                    print(f"加载行业分类映射表失败: {e}")
    
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
    
    def batch_check_kline_cache_status(self, stock_codes: List[str], 
                                       show_progress: bool = False) -> Dict[str, str]:
        """
        批量检查股票K线缓存状态
        Args:
            stock_codes: 股票代码列表
            show_progress: 是否显示进度
        Returns:
            缓存状态字典 {stock_code: status}
            status值: 'latest'=有最新缓存, 'outdated'=有旧缓存, 'missing'=无缓存
        """
        from tqdm import tqdm
        
        cache_status = {}
        
        if show_progress:
            progress_bar = tqdm(total=len(stock_codes), desc="检查缓存状态", disable=False, leave=False)
        else:
            progress_bar = None
        
        for stock_code in stock_codes:
            clean_code = self._format_stock_code(stock_code)
            
            # 检查是否有最新交易日数据
            if not self.force_refresh and self.cache_manager.has_latest_trading_day_data(clean_code, 'stock', 'daily'):
                cache_status[stock_code] = 'latest'
            else:
                # 检查是否有旧缓存
                cached_kline = self.cache_manager.get_kline(clean_code, 'stock', 'daily', self.force_refresh)
                if cached_kline is not None and not cached_kline.empty:
                    cache_status[stock_code] = 'outdated'
                else:
                    cache_status[stock_code] = 'missing'
            
            if progress_bar:
                progress_bar.update(1)
        
        if progress_bar:
            progress_bar.close()
        
        # 统计
        latest_count = sum(1 for status in cache_status.values() if status == 'latest')
        outdated_count = sum(1 for status in cache_status.values() if status == 'outdated')
        missing_count = sum(1 for status in cache_status.values() if status == 'missing')
        
        # 不在这个方法中打印，由调用方统一打印
        # if show_progress:
        #     print(f"缓存状态: 最新 {latest_count} 只 | 需更新 {outdated_count} 只 | 缺失 {missing_count} 只")
        
        return cache_status
    
    def batch_load_cached_kline(self, stock_codes: List[str], 
                                show_progress: bool = False) -> Dict[str, pd.DataFrame]:
        """
        批量加载已缓存的K线数据到内存
        Args:
            stock_codes: 股票代码列表（只加载这些股票的缓存）
            show_progress: 是否显示进度
        Returns:
            K线数据字典 {stock_code: kline_dataframe}
        """
        from tqdm import tqdm
        
        cached_data = {}
        
        if show_progress:
            progress_bar = tqdm(total=len(stock_codes), desc="  进度", 
                               bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]',
                               disable=False, leave=False)
        else:
            progress_bar = None
        
        for stock_code in stock_codes:
            clean_code = self._format_stock_code(stock_code)
            
            try:
                # 从缓存加载
                kline_data = self.cache_manager.get_kline(clean_code, 'stock', 'daily', False)
                if kline_data is not None and not kline_data.empty:
                    # 如果应该使用昨天的数据，过滤掉今天的数据
                    use_yesterday = should_use_yesterday_data()
                    if use_yesterday and 'date' in kline_data.columns:
                        kline_data['date'] = pd.to_datetime(kline_data['date'])
                        today = datetime.now().date()
                        kline_data = kline_data[kline_data['date'].dt.date < today]
                    
                    if not kline_data.empty:
                        cached_data[stock_code] = kline_data
            except Exception as e:
                if self.progress_callback:
                    self.progress_callback('warning', f"加载 {stock_code} 缓存失败: {e}")
            
            if progress_bar:
                progress_bar.update(1)
        
        if progress_bar:
            progress_bar.close()
        
        return cached_data
    
    def batch_get_stock_kline(self, stock_codes: List[str], start_date: str = None, 
                             end_date: str = None, show_progress: bool = False) -> Dict[str, pd.DataFrame]:
        """
        批量获取股票K线数据（使用按日期批量查询方式，大幅提升效率）
        
        优化说明：
        - 传统方式：每只股票单独调用API，2184只股票需要2184次API调用
        - 批量方式：按日期批量获取，120个交易日只需120次API调用，效率提升约18倍
        
        Args:
            stock_codes: 股票代码列表
            start_date: 开始日期，格式'YYYYMMDD'，None表示使用默认（最近120天）
            end_date: 结束日期，格式'YYYYMMDD'，None表示使用默认（今天或昨天）
            show_progress: 是否显示进度
        Returns:
            股票K线数据字典 {stock_code: kline_dataframe}
        """
        from tqdm import tqdm
        
        # 如果没有指定日期，使用默认日期范围
        use_yesterday = should_use_yesterday_data()
        analysis_date = get_analysis_date()
        
        if start_date is None:
            start_date = (analysis_date - timedelta(days=120)).strftime('%Y%m%d')
        
        if end_date is None:
            if use_yesterday:
                end_date_obj = analysis_date - timedelta(days=1)
                while end_date_obj.weekday() >= 5:
                    end_date_obj = end_date_obj - timedelta(days=1)
                end_date = end_date_obj.strftime('%Y%m%d')
            else:
                end_date = analysis_date.strftime('%Y%m%d')
        
        # 获取交易日列表
        def get_trading_dates(start: str, end: str) -> List[str]:
            """获取交易日列表"""
            try:
                self._wait_before_request()
                cal_df = self.pro.trade_cal(exchange='SSE', start_date=start, end_date=end, is_open=1)
                if cal_df is not None and not cal_df.empty:
                    return cal_df['cal_date'].tolist()
                return []
            except Exception as e:
                if self.progress_callback:
                    self.progress_callback('warning', f"获取交易日历失败: {e}")
                return []
        
        trading_dates = get_trading_dates(start_date, end_date)
        if not trading_dates:
            if self.progress_callback:
                self.progress_callback('error', "无法获取交易日列表，回退到单股票查询模式")
            return {}
        
        # 准备股票代码映射（6位代码 -> ts_code格式）
        stock_code_map = {}  # {6位代码: ts_code}
        ts_code_to_clean = {}  # {ts_code: 6位代码}
        for code in stock_codes:
            clean_code = self._format_stock_code(code)
            ts_code = self._get_ts_code(clean_code)
            if ts_code:
                stock_code_map[clean_code] = ts_code
                ts_code_to_clean[ts_code] = clean_code
        
        if not stock_code_map:
            return {}
        
        # 按日期批量获取数据
        all_data_list = []
        date_progress = tqdm(trading_dates, desc="  按日期获取", disable=not show_progress, leave=False)
        
        for trade_date in date_progress:
            try:
                self._wait_before_request()
                
                # 使用trade_date参数批量获取该日期的所有股票数据
                df = self.pro.daily(trade_date=trade_date)
                
                if df is not None and not df.empty:
                    # 只保留我们需要的股票
                    df = df[df['ts_code'].isin(stock_code_map.values())]
                    if not df.empty:
                        all_data_list.append(df)
                
                date_progress.set_postfix({'已获取': len(all_data_list), '当前日期': trade_date})
            except Exception as e:
                if self.progress_callback:
                    self.progress_callback('warning', f"获取日期 {trade_date} 的数据失败: {e}")
                continue
        
        if show_progress:
            date_progress.close()
        
        if not all_data_list:
            if self.progress_callback:
                self.progress_callback('warning', "批量获取未获取到任何数据")
            return {}
        
        # 合并所有日期的数据
        combined_df = pd.concat(all_data_list, ignore_index=True)
        
        # 重命名列
        combined_df.rename(columns={
            'trade_date': 'date',
            'vol': 'volume',
            'amount': 'turnover',
            'pct_chg': 'pct_change',
        }, inplace=True)
        
        # 转换日期格式
        combined_df['date'] = pd.to_datetime(combined_df['date'], format='%Y%m%d')
        
        # 按股票代码分组
        result_dict = {}
        grouped = combined_df.groupby('ts_code')
        
        if show_progress:
            stock_progress = tqdm(stock_code_map.items(), desc="  处理数据", disable=False, leave=False)
        else:
            stock_progress = stock_code_map.items()
        
        for clean_code, ts_code in stock_progress:
            if ts_code in grouped.groups:
                stock_df = grouped.get_group(ts_code).copy()
                stock_df = stock_df.sort_values('date')
                
                # 添加换手率列（默认值，后续可以通过daily_basic批量获取）
                stock_df['turnover_rate'] = 0
                
                # 确保必要的列存在
                required_columns = ['date', 'open', 'close', 'high', 'low', 'volume']
                for col in required_columns:
                    if col not in stock_df.columns:
                        stock_df[col] = 0
                
                # 如果应该使用昨天的数据，过滤掉今天的数据
                if use_yesterday:
                    today = datetime.now().date()
                    stock_df = stock_df[stock_df['date'].dt.date < today]
                
                if not stock_df.empty:
                    result_dict[clean_code] = stock_df[['date', 'open', 'close', 'high', 'low', 
                                                        'volume', 'turnover', 'pct_change', 'turnover_rate']]
        
        # 不在这个方法中打印，由调用方统一打印
        # if show_progress:
        #     print(f"获取完成：成功 {len(result_dict)} 只")
        
        return result_dict
    
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
        优化：使用日期范围参数获取数据，更稳定；保留None值，不转换为0
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
                # 使用日期范围参数获取数据（参考 get_stock_kline 的实现）
                # 获取最近5个交易日的数据，确保能获取到有效数据
                analysis_date = get_analysis_date()
                end_date = analysis_date.strftime('%Y%m%d')
                start_date = (analysis_date - timedelta(days=7)).strftime('%Y%m%d')  # 往前推7天，确保覆盖5个交易日
                
                # 使用 start_date 和 end_date 参数，更稳定
                df = self.pro.daily_basic(ts_code=ts_code, 
                                         start_date=start_date, 
                                         end_date=end_date,
                                         fields='ts_code,trade_date,pe,pb,ps,turnover_rate')
                
                if df is not None and not df.empty:
                    # 按日期排序，取最新的数据
                    df = df.sort_values('trade_date', ascending=False)
                    latest = df.iloc[0]
                    
                    # 改进 None/NaN 值处理：保留 None，不转换为 0
                    # 区分"值为0"（可能是正常值）和"值为None/NaN"（数据缺失）
                    def safe_float_or_none(value):
                        """安全转换为float，保留None/NaN"""
                        if value is None:
                            return None
                        if isinstance(value, float) and pd.isna(value):
                            return None
                        try:
                            if isinstance(value, str):
                                value = value.replace(',', '').replace('--', '').replace('-', '')
                                if not value or value == '':
                                    return None
                            result = float(value)
                            # 如果转换后为0，但原始值不是0，可能是转换错误
                            return result
                        except (ValueError, TypeError):
                            return None
                    
                    return {
                        'pe_ratio': safe_float_or_none(latest.get('pe')),
                        'pb_ratio': safe_float_or_none(latest.get('pb')),
                        'ps_ratio': safe_float_or_none(latest.get('ps')),
                        'turnover_rate': safe_float_or_none(latest.get('turnover_rate')),
                    }
                return None
            
            result = self._retry_request(fetch_fundamental, max_retries=3, timeout=15)
            
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
        获取股票所属板块（使用 index_classify + index_member，带缓存）
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
        
        # 加载行业映射表（如果未加载）
        if not self._industry_map_loaded:
            self._load_industry_mapping()
        
        # 从映射表获取
        try:
            with self._industry_map_lock:
                sectors = self._stock_industry_map.get(clean_code, [])
            
            if sectors:
                # 保存到缓存
                self.cache_manager.save_stock_sectors(clean_code, sectors)
                return sectors
        except Exception as e:
            if self.progress_callback:
                self.progress_callback('warning', f"获取 {stock_code} 板块信息失败: {e}")
            else:
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
                # 正确方式：先获取所有概念列表，然后遍历每个概念检查是否包含该股票
                try:
                    # 1. 获取所有概念列表
                    all_concepts_df = self.pro.concept()
                    if all_concepts_df is None or all_concepts_df.empty:
                        return []
                    
                    # 2. 遍历每个概念，检查是否包含该股票
                    stock_concepts = []
                    for _, concept_row in all_concepts_df.iterrows():
                        # concept接口返回的字段是code
                        concept_id = concept_row.get('code') or concept_row.get('id')
                        concept_name = concept_row.get('name', '')
                        
                        if not concept_id or not concept_name:
                            continue
                        
                        try:
                            # 获取该概念的股票列表
                            stocks_df = self.pro.concept_detail(id=concept_id, fields='ts_code')
                            if stocks_df is not None and not stocks_df.empty:
                                # 检查该股票是否在该概念的股票列表中
                                if ts_code in stocks_df['ts_code'].values:
                                    stock_concepts.append(concept_name.strip())
                            
                            # 控制请求频率，避免超过API限制
                            import time
                            time.sleep(self.min_request_interval)
                        except Exception as e:
                            # 某个概念获取失败，继续下一个
                            # 如果是权限问题，停止遍历
                            if "积分" in str(e) or "权限" in str(e) or "最多访问" in str(e):
                                break
                            continue
                    
                    return stock_concepts
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
    
    def get_sector_kline(self, sector_name: str, period: str = "daily", 
                        check_cache_only: bool = False) -> Optional[pd.DataFrame]:
        """
        获取板块K线数据（支持内存缓存和磁盘缓存）
        使用行业代码直接获取指数K线数据（基于 index_classify）
        Args:
            sector_name: 板块名称
            period: 周期 ('daily', 'weekly', 'monthly')
            check_cache_only: 如果为True，只检查缓存，不请求外部数据
        Returns:
            板块K线数据DataFrame，如果check_cache_only=True且缓存不存在则返回None
        """
        try:
            # 检查内存缓存
            cache_key = f"{sector_name}_{period}"
            with self._cache_lock:
                if cache_key in self._sector_kline_cache:
                    return self._sector_kline_cache[cache_key].copy()
            
            # 检查磁盘缓存（优先检查是否有最新交易日数据）
            if not self.force_refresh:
                # 先检查是否有最新交易日数据（快速检查）
                if self.cache_manager.has_latest_trading_day_data(sector_name, 'sector', period):
                    cached_kline = self.cache_manager.get_kline(sector_name, 'sector', period, False)
                    if cached_kline is not None and not cached_kline.empty:
                        # 存入内存缓存
                        with self._cache_lock:
                            self._sector_kline_cache[cache_key] = cached_kline
                        return cached_kline
                else:
                    # 检查是否有旧缓存（用于增量更新）
                    cached_kline = self.cache_manager.get_kline(sector_name, 'sector', period, False)
                    if cached_kline is not None and not cached_kline.empty:
                        # 存入内存缓存（但标记为需要更新）
                        with self._cache_lock:
                            self._sector_kline_cache[cache_key] = cached_kline
                        # 如果只检查缓存，直接返回旧缓存
                        if check_cache_only:
                            return cached_kline
                        # 否则继续，准备增量更新
            
            # 如果只检查缓存，且缓存不存在，返回None
            if check_cache_only:
                return None
            
            # 加载行业映射表（如果未加载）
            if not self._industry_map_loaded:
                self._load_industry_mapping()
            
            # 通过行业代码直接获取指数K线数据
            def fetch_sector_kline():
                sector_name_clean = sector_name.strip()
                
                # 从映射表获取行业代码
                with self._industry_map_lock:
                    index_code = self._industry_index_map.get(sector_name_clean)
                
                # 如果映射表中没有，尝试直接匹配（兼容旧代码）
                if not index_code:
                    # 尝试获取行业指数列表并匹配
                    index_df = self.pro.index_basic(market='SW', fields='ts_code,name')
                    if index_df is not None and not index_df.empty:
                        for _, row in index_df.iterrows():
                            index_name = row['name']
                            if '退市' in index_name:
                                continue
                            if sector_name_clean in index_name or index_name in sector_name_clean:
                                index_code = row['ts_code']
                                break
                
                if not index_code:
                    if self.progress_callback:
                        self.progress_callback('warning', f"板块 '{sector_name}': 未找到对应的指数代码")
                    return None
                
                # 获取指数K线数据（支持增量更新）
                analysis_date = get_analysis_date()
                end_date = analysis_date.strftime('%Y%m%d')
                
                # 检查是否有旧缓存，用于增量更新
                cached_latest_date = None
                if not self.force_refresh:
                    cached_kline = self.cache_manager.get_kline(sector_name, 'sector', period, False)
                    if cached_kline is not None and not cached_kline.empty and 'date' in cached_kline.columns:
                        cached_kline['date'] = pd.to_datetime(cached_kline['date'])
                        cached_latest_date = cached_kline['date'].max()
                
                # 确定起始日期
                if cached_latest_date is not None:
                    # 从缓存最新日期的下一天开始（增量更新）
                    start_date_obj = cached_latest_date + timedelta(days=1)
                    # 如果下一天是周末，跳到下一个工作日
                    while start_date_obj.weekday() >= 5:
                        start_date_obj = start_date_obj + timedelta(days=1)
                    start_date = start_date_obj.strftime('%Y%m%d')
                    
                    # 如果start_date >= end_date，说明缓存已是最新，直接返回缓存
                    if start_date >= end_date:
                        return cached_kline if cached_kline is not None else None
                else:
                    # 没有缓存，获取最近120天的数据
                    start_date = (analysis_date - timedelta(days=120)).strftime('%Y%m%d')
                
                try:
                    kline_df = self.pro.index_daily(ts_code=index_code, start_date=start_date, end_date=end_date)
                    if kline_df is None or kline_df.empty:
                        if self.progress_callback:
                            self.progress_callback('warning', f"板块 '{sector_name}' (指数代码: {index_code}): index_daily返回空数据")
                        return None
                except Exception as e:
                    error_msg = str(e)
                    if self.progress_callback:
                        self.progress_callback('error', f"板块 '{sector_name}' (指数代码: {index_code}): index_daily调用失败 - {error_msg[:100]}")
                    # 检查是否是权限问题
                    if '权限' in error_msg or '积分' in error_msg or 'token' in error_msg.lower():
                        if self.progress_callback:
                            self.progress_callback('error', f"板块 '{sector_name}': index_daily可能需要更高积分或权限（当前积分: 2100）")
                    return None
                
                # 格式化数据
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
                # 增量更新：如果有旧缓存，合并新旧数据
                if not self.force_refresh:
                    cached_kline = self.cache_manager.get_kline(sector_name, 'sector', period, False)
                    if cached_kline is not None and not cached_kline.empty and not sector_kline.empty:
                        if 'date' in sector_kline.columns and 'date' in cached_kline.columns:
                            sector_kline['date'] = pd.to_datetime(sector_kline['date'])
                            cached_kline['date'] = pd.to_datetime(cached_kline['date'])
                            # 合并：保留旧数据，追加新数据
                            combined_kline = pd.concat([cached_kline, sector_kline], ignore_index=True)
                            # 按日期排序并去重（保留最新的）
                            combined_kline = combined_kline.sort_values('date').drop_duplicates(subset=['date'], keep='last')
                            sector_kline = combined_kline
                
                # 存入内存缓存
                with self._cache_lock:
                    self._sector_kline_cache[cache_key] = sector_kline
                
                # 批量模式：收集到批量缓存中，稍后统一保存
                if self.batch_mode:
                    with self._batch_lock:
                        self.sector_kline_batch[sector_name] = {
                            'data': sector_kline,
                            'period': period
                        }
                else:
                    # 立即保存到磁盘缓存
                    self.cache_manager.save_kline(sector_name, sector_kline, 'sector', period, incremental=True)
                
                return sector_kline
            
        except Exception as e:
            error_msg = str(e)
            if self.progress_callback:
                self.progress_callback('error', f"获取板块 {sector_name} K线数据失败: {error_msg[:100]}")
            else:
                print(f"获取板块 {sector_name} K线数据失败: {error_msg}")
            # 检查是否是权限或积分问题
            if '权限' in error_msg or '积分' in error_msg or 'token' in error_msg.lower():
                if self.progress_callback:
                    self.progress_callback('error', f"提示: index_daily接口可能需要2000积分以上，请检查Tushare积分和权限")
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
        # 优化：延迟加载股票列表（按需加载）
        if self.stock_list is None or self.stock_list.empty:
            self._load_stock_list()
        
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
        total_count = 0
        
        try:
            with self._batch_lock:
                if self.fundamental_batch:
                    batch_to_save = self.fundamental_batch.copy()
                    self.fundamental_batch.clear()
                else:
                    batch_to_save = {}
            
            if batch_to_save:
                self.cache_manager.batch_save_fundamental(batch_to_save)
                total_count += len(batch_to_save)
        except Exception as e:
            print(f"批量保存基本面缓存失败: {e}")
        
        try:
            with self._batch_lock:
                if self.financial_batch:
                    batch_to_save = self.financial_batch.copy()
                    self.financial_batch.clear()
                else:
                    batch_to_save = {}
            
            if batch_to_save:
                self.cache_manager.batch_save_financial(batch_to_save)
                total_count += len(batch_to_save)
        except Exception as e:
            print(f"批量保存财务缓存失败: {e}")
        
        # 批量保存板块K线缓存
        try:
            with self._batch_lock:
                if self.sector_kline_batch:
                    batch_to_save = self.sector_kline_batch.copy()
                    self.sector_kline_batch.clear()
                else:
                    batch_to_save = {}
            
            if batch_to_save:
                for sector_name, sector_info in batch_to_save.items():
                    try:
                        self.cache_manager.save_kline(
                            sector_name, 
                            sector_info['data'], 
                            'sector', 
                            sector_info['period'], 
                            incremental=True
                        )
                        total_count += 1
                    except Exception as e:
                        print(f"批量保存板块 {sector_name} K线缓存失败: {e}")
        except Exception as e:
            print(f"批量保存板块K线缓存失败: {e}")
        
        return total_count
    
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
    
    def batch_preload_sector_kline(self, sector_names: List[str], period: str = "daily",
                                   max_workers: int = 5, show_progress: bool = True) -> Dict[str, pd.DataFrame]:
        """
        批量预加载板块K线数据（优化：先检查缓存，缓存不存在或过期才请求）
        Args:
            sector_names: 板块名称列表
            period: 周期 ('daily', 'weekly', 'monthly')
            max_workers: 最大线程数
            show_progress: 是否显示进度
        Returns:
            板块K线数据字典 {sector_name: kline_data}
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from tqdm import tqdm
        
        if not sector_names:
            return {}
        
        # 去重
        unique_sectors = list(set(sector_names))
        total = len(unique_sectors)
        
        if show_progress:
            print(f"\n开始批量预加载 {total} 个板块的K线数据...")
            print("=" * 60)
        
        # 步骤1: 先批量检查缓存，收集需要请求的板块
        sectors_to_fetch = []
        sector_kline_results = {}
        
        if show_progress:
            print("步骤1: 检查板块K线缓存...")
        
        for sector_name in unique_sectors:
            # 先检查缓存（不请求外部数据）
            cached_kline = self.get_sector_kline(sector_name, period, check_cache_only=True)
            if cached_kline is not None and not cached_kline.empty:
                # 检查是否有最新交易日数据
                if self.cache_manager.has_latest_trading_day_data(sector_name, 'sector', period):
                    sector_kline_results[sector_name] = cached_kline
                    if show_progress:
                        print(f"  ✓ {sector_name}: 使用缓存数据")
                else:
                    # 缓存过期，需要更新
                    sectors_to_fetch.append(sector_name)
                    if show_progress:
                        print(f"  ⚠ {sector_name}: 缓存过期，需要更新")
            else:
                # 缓存不存在，需要请求
                sectors_to_fetch.append(sector_name)
                if show_progress:
                    print(f"  ✗ {sector_name}: 缓存不存在，需要请求")
        
        cached_count = len(sector_kline_results)
        fetch_count = len(sectors_to_fetch)
        
        if show_progress:
            print(f"\n缓存统计: 已缓存 {cached_count} 个，需要请求 {fetch_count} 个")
            print("=" * 60)
        
        # 步骤2: 批量请求需要更新的板块K线数据
        if sectors_to_fetch:
            if show_progress:
                print(f"\n步骤2: 批量请求 {fetch_count} 个板块的K线数据...")
                print("=" * 60)
            
            # 启用批量模式
            self.batch_mode = True
            
            def fetch_single_sector(sector_name: str) -> tuple:
                """获取单个板块的K线数据"""
                try:
                    kline = self.get_sector_kline(sector_name, period, check_cache_only=False)
                    if kline is not None and not kline.empty:
                        return (sector_name, kline, True)
                    else:
                        return (sector_name, None, False)
                except Exception as e:
                    if show_progress:
                        print(f"  获取板块 {sector_name} K线失败: {e}")
                    return (sector_name, None, False)
            
            # 使用线程池并行请求
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(fetch_single_sector, sector): sector 
                          for sector in sectors_to_fetch}
                
                if show_progress:
                    pbar = tqdm(total=len(sectors_to_fetch), desc="板块K线请求进度",
                               bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]')
                
                success_count = 0
                for future in as_completed(futures):
                    sector_name, kline, success = future.result()
                    if success and kline is not None:
                        sector_kline_results[sector_name] = kline
                        success_count += 1
                    if show_progress:
                        pbar.update(1)
                
                if show_progress:
                    pbar.close()
            
            # 批量保存板块K线缓存
            if show_progress:
                print(f"\n步骤3: 批量保存板块K线缓存...")
            
            saved_count = self.flush_batch_cache()
            self.batch_mode = False
            
            if show_progress:
                print(f"  已保存 {saved_count} 个板块的K线缓存")
        else:
            if show_progress:
                print("\n所有板块K线数据都已缓存，无需请求")
        
        if show_progress:
            print("\n" + "=" * 60)
            print(f"板块K线预加载完成！")
            print(f"  总计: {total} 个板块")
            print(f"  已缓存: {cached_count} 个")
            print(f"  新请求: {fetch_count} 个")
            print(f"  成功: {len(sector_kline_results)} 个")
            print("=" * 60)
        
        return sector_kline_results
    
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

