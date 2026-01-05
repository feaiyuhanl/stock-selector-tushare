"""
数据获取器基础模块：初始化、请求控制、工具方法
"""
import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
import time
import threading
from typing import Dict, List, Optional
from .cache_manager import CacheManager
from .utils import (
    is_trading_time, 
    get_analysis_date, 
    should_use_yesterday_data,
    normalize_stock_code
)
import config
import os


class FetcherBase:
    """数据获取器基础类：提供初始化、请求控制、工具方法"""
    
    def __init__(self, force_refresh: bool = False, progress_callback=None, test_sources: bool = True):
        """
        初始化数据获取器基础功能
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
        return normalize_stock_code(stock_code)
    
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
    
    def _safe_float(self, value) -> float:
        """安全转换为float"""
        try:
            if isinstance(value, str):
                value = value.replace(',', '').replace('--', '0').replace('-', '0')
            return float(value) if value else 0.0
        except:
            return 0.0
    
    def _extract_yearly_data(self, income_df: pd.DataFrame) -> pd.DataFrame:
        """
        从利润表数据中提取年度数据
        选择每年最后一个报告期的数据作为年度数据
        """
        if income_df is None or income_df.empty:
            return pd.DataFrame()

        # 确保end_date是datetime类型
        income_df = income_df.copy()
        income_df['end_date'] = pd.to_datetime(income_df['end_date'])
        income_df['year'] = income_df['end_date'].dt.year

        # 为每个年度选择最后一个报告期的数据
        yearly_data = income_df.sort_values('end_date').groupby('year').last().reset_index()

        return yearly_data
    
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
                # 筛选板块 - 延迟导入避免循环依赖
                from .fetcher import filter_stocks_by_board
                filtered = filter_stocks_by_board(self.stock_list, board_types)
                return filtered['code'].tolist()
        return []
    
    def get_trade_calendar(self, start_date: str = None, end_date: str = None, 
                          force_refresh: bool = False) -> Optional[pd.DataFrame]:
        """
        获取交易日历（带缓存，1周刷新一次）
        Args:
            start_date: 开始日期，格式：YYYYMMDD，如果为None则使用当前日期往前推1年
            end_date: 结束日期，格式：YYYYMMDD，如果为None则使用当前日期往后推1年
            force_refresh: 是否强制刷新缓存
        Returns:
            交易日历DataFrame，包含 cal_date 和 is_open 列
        """
        try:
            # 先尝试从缓存读取
            if not force_refresh:
                cached_cal = self.cache_manager.get_trade_calendar(force_refresh)
                if cached_cal is not None and not cached_cal.empty:
                    # 检查缓存是否包含需要的日期范围
                    need_fetch = False
                    if start_date or end_date:
                        cached_cal['cal_date'] = cached_cal['cal_date'].astype(str)
                        if start_date and cached_cal['cal_date'].min() > start_date:
                            # 缓存中没有开始日期之前的数据，需要获取
                            need_fetch = True
                        elif end_date and cached_cal['cal_date'].max() < end_date:
                            # 缓存中没有结束日期之后的数据，需要获取
                            need_fetch = True
                    
                    if not need_fetch:
                        # 缓存包含所需范围，直接返回
                        return cached_cal
                    # 如果需要获取，继续执行后面的API调用逻辑
            
            # 从API获取交易日历
            if self.progress_callback:
                self.progress_callback('loading', "从网络获取交易日历...")
            
            # 如果没有指定日期范围，获取当前日期前后各1年的数据
            if start_date is None:
                start_date_obj = datetime.now() - timedelta(days=365)
                start_date = start_date_obj.strftime('%Y%m%d')
            if end_date is None:
                end_date_obj = datetime.now() + timedelta(days=365)
                end_date = end_date_obj.strftime('%Y%m%d')
            
            def fetch_trade_cal():
                # 获取交易日历（SSE=上海证券交易所）
                df = self.pro.trade_cal(exchange='SSE', start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    # 确保列名正确（cal_date 和 is_open）
                    if 'cal_date' not in df.columns and 'exchangeCalDate' in df.columns:
                        df.rename(columns={'exchangeCalDate': 'cal_date'}, inplace=True)
                    if 'is_open' not in df.columns and 'isOpen' in df.columns:
                        df.rename(columns={'isOpen': 'is_open'}, inplace=True)
                    return df[['cal_date', 'is_open']] if 'cal_date' in df.columns and 'is_open' in df.columns else df
                return None
            
            trade_cal = self._retry_request(fetch_trade_cal, max_retries=3, timeout=30)
            
            if trade_cal is not None and not trade_cal.empty:
                # 保存到缓存
                self.cache_manager.save_trade_calendar(trade_cal)
                msg = f"成功获取交易日历 {len(trade_cal)} 条记录"
                if self.progress_callback:
                    self.progress_callback('success', msg)
                else:
                    print(msg)
                return trade_cal
            else:
                error_msg = "获取交易日历失败：返回数据为空"
                if self.progress_callback:
                    self.progress_callback('failed', error_msg)
                else:
                    print(error_msg)
                return None
                
        except Exception as e:
            error_msg = f"获取交易日历失败: {e}"
            if self.progress_callback:
                self.progress_callback('failed', error_msg)
            else:
                print(error_msg)
            return None
    
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
        注意：此方法需要在DataFetcher类中实现，因为它需要访问kline_fetcher和fundamental_fetcher
        """
        # 这个方法将在DataFetcher中实现，因为它需要访问子模块
        raise NotImplementedError("preload_stock_data should be called on DataFetcher instance")

