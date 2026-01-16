"""
指数权重策略数据加载器：确保指数权重数据已加载
"""
from datetime import datetime, timedelta
from data.utils import get_analysis_date


class IndexDataLoader:
    """指数权重策略数据加载器"""
    
    def __init__(self, data_fetcher, index_codes, lookback_days, force_refresh, index_names):
        """
        初始化数据加载器
        Args:
            data_fetcher: 数据获取器
            index_codes: 要追踪的指数代码列表
            lookback_days: 回看天数
            force_refresh: 是否强制刷新缓存
            index_names: 指数名称映射
        """
        self.data_fetcher = data_fetcher
        self.index_codes = index_codes
        self.lookback_days = lookback_days
        self.force_refresh = force_refresh
        self.index_names = index_names
    
    def ensure_index_weight_data(self):
        """
        确保指数权重数据已加载（如果缺失则自动获取）
        智能判断是否需要刷新：使用 get_analysis_date() 来确定应该使用的交易日，
        并检查缓存中是否有该交易日的数据（类似 K线数据的处理方式）
        """
        print("  检查指数权重数据缓存...")
        
        # 获取应该使用的分析日期（考虑交易时间、节假日等）
        analysis_date = get_analysis_date()
        analysis_date_str = analysis_date.strftime('%Y%m%d')
        
        # 计算需要获取的日期范围（多获取一些天数，确保有足够的历史数据）
        end_date = datetime.now().strftime('%Y%m%d')
        # 获取更多历史数据，确保有足够的交易日数据
        start_date = (datetime.now() - timedelta(days=self.lookback_days * 2)).strftime('%Y%m%d')
        
        # 检查每个指数的数据完整性
        indices_to_fetch = []
        for index_code in self.index_codes:
            # 检查是否有最新数据
            latest_data = self.data_fetcher.cache_manager.get_index_weight(
                index_code=index_code,
                start_date=start_date,
                end_date=end_date,
                force_refresh=False
            )
            
            if latest_data is None or latest_data.empty:
                indices_to_fetch.append(index_code)
                print(f"    {self.index_names.get(index_code, index_code)}: 数据缺失，需要获取")
            else:
                # 检查数据日期范围和数据点数量
                dates = latest_data['trade_date'].unique()
                date_count = len(dates)
                # 计算最小要求：至少需要足够的数据点来计算趋势（至少3个点，理想情况下是回看天数的1/3）
                # 但考虑到非交易日，实际需要的数据点会少于回看天数
                # 降低要求：至少3个数据点即可进行基本分析，理想情况是回看天数的1/4
                min_required = max(3, self.lookback_days // 4)
                # 如果已经有10个以上的数据点，认为数据足够
                ideal_required = max(10, self.lookback_days // 3)
                
                # 检查最新数据日期，判断是否需要更新
                if dates.size > 0:
                    latest_date = max(dates)
                    # 使用分析日期来判断是否需要更新（而不是简单的 today）
                    # 如果缓存中的最新日期早于应该使用的分析日期，则需要更新
                    needs_update = latest_date < analysis_date_str
                else:
                    latest_date = None
                    needs_update = True
                
                if date_count < min_required:
                    # 数据严重不足，必须获取
                    indices_to_fetch.append(index_code)
                    print(f"    {self.index_names.get(index_code, index_code)}: 数据不足 ({date_count} 个交易日，需要至少 {min_required} 个)，需要获取")
                elif needs_update:
                    # 数据基本足够但需要更新到最新日期
                    indices_to_fetch.append(index_code)
                    print(f"    {self.index_names.get(index_code, index_code)}: 数据可更新 ({date_count} 个交易日，最新: {latest_date}，需要: {analysis_date_str})，将更新到最新日期")
                else:
                    # 数据完整且最新
                    print(f"    {self.index_names.get(index_code, index_code)}: 数据完整 ({date_count} 个交易日，最新: {latest_date})")
        
        # 批量获取缺失的数据
        if indices_to_fetch:
            print(f"\n  获取 {len(indices_to_fetch)} 个指数的权重数据...")
            print(f"  日期范围: {start_date} 至 {end_date}")
            self.data_fetcher.batch_get_index_weight(
                index_codes=indices_to_fetch,
                start_date=start_date,
                end_date=end_date,
                force_refresh=self.force_refresh,
                show_progress=True
            )
            print("  ✓ 指数权重数据获取完成")

