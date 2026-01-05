"""
交易日历工具函数
"""
from datetime import datetime, timedelta


def is_trading_day_after_15_00(data_fetcher=None) -> bool:
    """
    判断当前是否是交易日且在15:00之后（使用tushare交易日历）
    Args:
        data_fetcher: DataFetcher实例，用于获取交易日历。如果为None，会创建一个临时实例
    Returns:
        如果是交易日且当前时间在15:00之后，返回True；否则返回False
    """
    now = datetime.now()
    current_time = now.time()
    
    # 检查是否在15:00之后
    cutoff_time = datetime.strptime('15:00', '%H:%M').time()
    if current_time < cutoff_time:
        return False
    
    # 使用交易日历判断今天是否是交易日
    try:
        # 如果没有提供data_fetcher，创建一个临时实例
        if data_fetcher is None:
            from data.fetcher import DataFetcher
            data_fetcher = DataFetcher(test_sources=False)
        
        # 获取今天的日期（YYYYMMDD格式）
        today_str = now.strftime('%Y%m%d')
        
        # 先从缓存检查
        is_open = data_fetcher.cache_manager.is_trading_day(today_str)
        
        # 如果缓存中没有，获取交易日历
        if is_open is None:
            # 获取交易日历（包含今天）
            trade_cal = data_fetcher.get_trade_calendar(
                start_date=(now - timedelta(days=30)).strftime('%Y%m%d'),
                end_date=(now + timedelta(days=30)).strftime('%Y%m%d'),
                force_refresh=False
            )
            
            if trade_cal is not None and not trade_cal.empty:
                # 查找今天的交易日状态
                today_row = trade_cal[trade_cal['cal_date'] == today_str]
                if not today_row.empty:
                    is_open = bool(today_row.iloc[0]['is_open'])
                else:
                    # 如果交易日历中没有今天的数据，使用周末判断作为后备
                    weekday = now.weekday()
                    is_open = weekday < 5  # 周一到周五
            else:
                # 如果获取交易日历失败，使用周末判断作为后备
                weekday = now.weekday()
                is_open = weekday < 5  # 周一到周五
        else:
            is_open = bool(is_open)
        
        return is_open
        
    except Exception as e:
        # 如果出现异常，使用周末判断作为后备
        print(f"[交易日判断] 获取交易日历失败，使用周末判断: {e}")
        weekday = now.weekday()
        is_open = weekday < 5  # 周一到周五
        return is_open

