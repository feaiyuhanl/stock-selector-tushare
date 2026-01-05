"""
K线数据获取模块
"""
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from .utils import should_use_yesterday_data, get_analysis_date


class KlineFetcher:
    """K线数据获取器"""
    
    def __init__(self, base):
        """
        初始化K线数据获取器
        Args:
            base: FetcherBase实例，提供基础功能
        """
        self.base = base
    
    def get_stock_kline(self, stock_code: str, period: str = "daily", 
                       start_date: str = None, end_date: str = None) -> Optional[pd.DataFrame]:
        """
        获取股票K线数据（支持缓存检查）
        period: daily, weekly, monthly
        """
        try:
            stock_code = str(stock_code)
            clean_code = self.base._format_stock_code(stock_code)
            
            # 确定是否应该使用昨天的数据
            use_yesterday = should_use_yesterday_data()
            analysis_date = get_analysis_date()
            
            # 智能检查：如果最新交易日数据已存在，直接返回
            if not self.base.force_refresh and self.base.cache_manager.has_latest_trading_day_data(clean_code, 'stock', period):
                cached_kline = self.base.cache_manager.get_kline(clean_code, 'stock', period, False)
                if cached_kline is not None and not cached_kline.empty:
                    if use_yesterday and 'date' in cached_kline.columns:
                        cached_kline['date'] = pd.to_datetime(cached_kline['date'])
                        today = datetime.now().date()
                        cached_kline = cached_kline[cached_kline['date'].dt.date < today]
                        if not cached_kline.empty:
                            if self.base.progress_callback:
                                self.base.progress_callback('cached', f"{clean_code}: 使用缓存数据（已过滤今日不完整数据）")
                            return cached_kline
                    else:
                        if self.base.progress_callback:
                            self.base.progress_callback('cached', f"{clean_code}: 最新交易日数据已存在，跳过下载")
                        return cached_kline
            
            # 检查其他缓存，用于增量更新
            cached_kline = self.base.cache_manager.get_kline(clean_code, 'stock', period, self.base.force_refresh)
            cached_latest_date = None
            if cached_kline is not None and not cached_kline.empty and not self.base.force_refresh:
                if self.base.progress_callback:
                    self.base.progress_callback('cached', f"{clean_code}: K线数据已缓存（非最新）")
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
                if self.base.progress_callback:
                    self.base.progress_callback('cached', f"{clean_code}: 缓存已是最新，无需更新")
                return cached_kline
            
            # 获取tushare代码格式（需要市场后缀）
            ts_code = self.base._get_ts_code(clean_code)
            if not ts_code:
                return None
            
            # 获取日K线数据
            def fetch_kline():
                # tushare的daily接口
                df = self.base.pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
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
                        basic_df = self.base.pro.daily_basic(ts_code=ts_code, start_date=start_date, end_date=end_date,
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
            
            kline = self.base._retry_request(fetch_kline, max_retries=3, timeout=30)
            
            if kline is None or kline.empty:
                # 如果重试后仍然失败，尝试从缓存读取
                cached_kline = self.base.cache_manager.get_kline(clean_code, 'stock', period, False)
                if cached_kline is not None and not cached_kline.empty:
                    if self.base.progress_callback:
                        self.base.progress_callback('cached', f"{clean_code}: 使用缓存K线数据（网络获取失败）")
                    return cached_kline
                return None
            
            # 如果应该使用昨天的数据，过滤掉今天的数据
            if use_yesterday and 'date' in kline.columns:
                today = datetime.now().date()
                original_count = len(kline)
                kline = kline[kline['date'].dt.date < today]
                if len(kline) < original_count:
                    if self.base.progress_callback:
                        self.base.progress_callback('info', f"{clean_code}: 已过滤今日不完整数据（{original_count} -> {len(kline)}条）")
            
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
                    if self.base.progress_callback:
                        self.base.progress_callback('info', f"{clean_code}: 增量更新完成（新增{len(kline) - len(cached_kline)}条数据）")
            
            # 保存到缓存（使用增量更新模式）
            self.base.cache_manager.save_kline(clean_code, kline, 'stock', period, incremental=True)
            
            return kline
        except Exception as e:
            error_msg = f"获取 {stock_code} K线数据失败: {e}"
            if self.base.progress_callback:
                self.base.progress_callback('failed', error_msg)
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
            clean_code = self.base._format_stock_code(stock_code)
            
            # 检查是否有最新交易日数据
            if not self.base.force_refresh and self.base.cache_manager.has_latest_trading_day_data(clean_code, 'stock', 'daily'):
                cache_status[stock_code] = 'latest'
            else:
                # 检查是否有旧缓存
                cached_kline = self.base.cache_manager.get_kline(clean_code, 'stock', 'daily', self.base.force_refresh)
                if cached_kline is not None and not cached_kline.empty:
                    cache_status[stock_code] = 'outdated'
                else:
                    cache_status[stock_code] = 'missing'
            
            if progress_bar:
                progress_bar.update(1)
        
        if progress_bar:
            progress_bar.close()
        
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
            clean_code = self.base._format_stock_code(stock_code)
            
            try:
                # 从缓存加载
                kline_data = self.base.cache_manager.get_kline(clean_code, 'stock', 'daily', False)
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
                if self.base.progress_callback:
                    self.base.progress_callback('warning', f"加载 {stock_code} 缓存失败: {e}")
            
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
                self.base._wait_before_request()
                cal_df = self.base.pro.trade_cal(exchange='SSE', start_date=start, end_date=end, is_open=1)
                if cal_df is not None and not cal_df.empty:
                    return cal_df['cal_date'].tolist()
                return []
            except Exception as e:
                if self.base.progress_callback:
                    self.base.progress_callback('warning', f"获取交易日历失败: {e}")
                return []
        
        trading_dates = get_trading_dates(start_date, end_date)
        if not trading_dates:
            if self.base.progress_callback:
                self.base.progress_callback('error', "无法获取交易日列表，回退到单股票查询模式")
            return {}
        
        # 准备股票代码映射（6位代码 -> ts_code格式）
        stock_code_map = {}  # {6位代码: ts_code}
        ts_code_to_clean = {}  # {ts_code: 6位代码}
        for code in stock_codes:
            clean_code = self.base._format_stock_code(code)
            ts_code = self.base._get_ts_code(clean_code)
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
                self.base._wait_before_request()
                
                # 使用trade_date参数批量获取该日期的所有股票数据
                df = self.base.pro.daily(trade_date=trade_date)
                
                if df is not None and not df.empty:
                    # 只保留我们需要的股票
                    df = df[df['ts_code'].isin(stock_code_map.values())]
                    if not df.empty:
                        all_data_list.append(df)
                
                date_progress.set_postfix({'已获取': len(all_data_list), '当前日期': trade_date})
            except Exception as e:
                if self.base.progress_callback:
                    self.base.progress_callback('warning', f"获取日期 {trade_date} 的数据失败: {e}")
                continue
        
        if show_progress:
            date_progress.close()
        
        if not all_data_list:
            if self.base.progress_callback:
                self.base.progress_callback('warning', "批量获取未获取到任何数据")
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
        
        return result_dict
    
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
            with self.base._cache_lock:
                if cache_key in self.base._sector_kline_cache:
                    return self.base._sector_kline_cache[cache_key].copy()
            
            # 检查磁盘缓存（优先检查是否有最新交易日数据）
            if not self.base.force_refresh:
                # 先检查是否有最新交易日数据（快速检查）
                if self.base.cache_manager.has_latest_trading_day_data(sector_name, 'sector', period):
                    cached_kline = self.base.cache_manager.get_kline(sector_name, 'sector', period, False)
                    if cached_kline is not None and not cached_kline.empty:
                        # 存入内存缓存
                        with self.base._cache_lock:
                            self.base._sector_kline_cache[cache_key] = cached_kline
                        return cached_kline
                else:
                    # 检查是否有旧缓存（用于增量更新）
                    cached_kline = self.base.cache_manager.get_kline(sector_name, 'sector', period, False)
                    if cached_kline is not None and not cached_kline.empty:
                        # 存入内存缓存（但标记为需要更新）
                        with self.base._cache_lock:
                            self.base._sector_kline_cache[cache_key] = cached_kline
                        # 如果只检查缓存，直接返回旧缓存
                        if check_cache_only:
                            return cached_kline
                        # 否则继续，准备增量更新
            
            # 如果只检查缓存，且缓存不存在，返回None
            if check_cache_only:
                return None
            
            # 加载行业映射表（如果未加载）
            if not self.base._industry_map_loaded:
                self.base._load_industry_mapping()
            
            # 通过行业代码直接获取指数K线数据
            def fetch_sector_kline():
                sector_name_clean = sector_name.strip()
                
                # 从映射表获取行业代码
                with self.base._industry_map_lock:
                    index_code = self.base._industry_index_map.get(sector_name_clean)
                
                # 如果映射表中没有，尝试直接匹配（兼容旧代码）
                if not index_code:
                    # 尝试获取行业指数列表并匹配
                    index_df = self.base.pro.index_basic(market='SW', fields='ts_code,name')
                    if index_df is not None and not index_df.empty:
                        for _, row in index_df.iterrows():
                            index_name = row['name']
                            if '退市' in index_name:
                                continue
                            if sector_name_clean in index_name or index_name in sector_name_clean:
                                index_code = row['ts_code']
                                break
                
                if not index_code:
                    if self.base.progress_callback:
                        self.base.progress_callback('warning', f"板块 '{sector_name}': 未找到对应的指数代码")
                    return None
                
                # 获取指数K线数据（支持增量更新）
                analysis_date = get_analysis_date()
                end_date = analysis_date.strftime('%Y%m%d')
                
                # 检查是否有旧缓存，用于增量更新
                cached_latest_date = None
                if not self.base.force_refresh:
                    cached_kline = self.base.cache_manager.get_kline(sector_name, 'sector', period, False)
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
                    kline_df = self.base.pro.index_daily(ts_code=index_code, start_date=start_date, end_date=end_date)
                    if kline_df is None or kline_df.empty:
                        if self.base.progress_callback:
                            self.base.progress_callback('warning', f"板块 '{sector_name}' (指数代码: {index_code}): index_daily返回空数据")
                        return None
                except Exception as e:
                    error_msg = str(e)
                    if self.base.progress_callback:
                        self.base.progress_callback('error', f"板块 '{sector_name}' (指数代码: {index_code}): index_daily调用失败 - {error_msg[:100]}")
                    # 检查是否是权限问题
                    if '权限' in error_msg or '积分' in error_msg or 'token' in error_msg.lower():
                        if self.base.progress_callback:
                            self.base.progress_callback('error', f"板块 '{sector_name}': index_daily可能需要更高积分或权限（当前积分: 2100）")
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
            
            sector_kline = self.base._retry_request(fetch_sector_kline, max_retries=2, timeout=20)
            
            if sector_kline is not None and not sector_kline.empty:
                # 增量更新：如果有旧缓存，合并新旧数据
                if not self.base.force_refresh:
                    cached_kline = self.base.cache_manager.get_kline(sector_name, 'sector', period, False)
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
                with self.base._cache_lock:
                    self.base._sector_kline_cache[cache_key] = sector_kline
                
                # 批量模式：收集到批量缓存中，稍后统一保存
                if self.base.batch_mode:
                    with self.base._batch_lock:
                        self.base.sector_kline_batch[sector_name] = {
                            'data': sector_kline,
                            'period': period
                        }
                else:
                    # 立即保存到磁盘缓存
                    self.base.cache_manager.save_kline(sector_name, sector_kline, 'sector', period, incremental=True)
                
                return sector_kline
            
        except Exception as e:
            error_msg = str(e)
            if self.base.progress_callback:
                self.base.progress_callback('error', f"获取板块 {sector_name} K线数据失败: {error_msg[:100]}")
            else:
                print(f"获取板块 {sector_name} K线数据失败: {error_msg}")
            # 检查是否是权限或积分问题
            if '权限' in error_msg or '积分' in error_msg or 'token' in error_msg.lower():
                if self.base.progress_callback:
                    self.base.progress_callback('error', f"提示: index_daily接口可能需要2000积分以上，请检查Tushare积分和权限")
        return None

