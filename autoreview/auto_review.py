"""
自动复盘核心模块
"""
from datetime import datetime, timedelta
from typing import List, Optional
import pandas as pd
from data.fetcher_base import FetcherBase
from data.cache_manager import CacheManager
from .review_cache import ReviewCache
from .review_helper import ReviewHelper, calculate_performance_score
import config


class AutoReview:
    """自动复盘管理器"""
    
    def __init__(self, data_fetcher: FetcherBase, cache_manager: CacheManager):
        """
        初始化自动复盘管理器
        Args:
            data_fetcher: 数据获取器
            cache_manager: 缓存管理器
        """
        self.data_fetcher = data_fetcher
        self.cache_manager = cache_manager
        self.review_cache = ReviewCache(cache_manager)
        self.review_helper = ReviewHelper(data_fetcher, cache_manager)
    
    def auto_review_last_n_days(self, days: int = None):
        """
        自动复盘最近N个交易日的推荐结果
        Args:
            days: 复盘天数，如果为None则使用配置中的默认值
        """
        if days is None:
            days = config.AUTO_REVIEW_CONFIG.get('review_days', 10)
        
        print("\n" + "=" * 60)
        print("【自动复盘】开始复盘前{}个交易日的推荐结果...".format(days))
        print("=" * 60)
        
        # 获取前N个交易日列表
        today = datetime.now().strftime('%Y%m%d')
        trading_dates = self._get_trading_dates_before(today, days)
        
        if not trading_dates:
            print("未找到交易日数据")
            return
        
        total_new = 0
        total_updated = 0
        processed_dates = 0
        
        for trade_date in trading_dates:
            processed = self.review_single_date(trade_date, days)
            if processed:
                new_count, updated_count = processed
                total_new += new_count
                total_updated += updated_count
                if new_count > 0 or updated_count > 0:
                    processed_dates += 1
        
        print("\n" + "=" * 60)
        print("【自动复盘完成】")
        print(f"  处理日期数: {processed_dates}/{len(trading_dates)}")
        print(f"  新增记录: {total_new} 条")
        print(f"  更新记录: {total_updated} 条")
        print("=" * 60)
    
    def review_single_date(self, trade_date: str, days: int = 10) -> Optional[tuple]:
        """
        复盘单个日期的推荐结果
        Args:
            trade_date: 推荐日期，格式：YYYYMMDD
            days: 复盘天数
        Returns:
            (新增记录数, 更新记录数) 元组，如果没有处理则返回None
        """
        from data.recommendation_cache import RecommendationCache
        recommendation_cache = RecommendationCache(self.cache_manager)
        
        # 获取推荐结果
        recommendations = recommendation_cache.get_recommendations(trade_date)
        
        if recommendations is None or recommendations.empty:
            return None
        
        new_count = 0
        updated_count = 0
        
        # 按策略分组处理
        for strategy_name in recommendations['strategy_name'].unique():
            strategy_recs = recommendations[recommendations['strategy_name'] == strategy_name]
            strategy_type = strategy_recs.iloc[0]['strategy_type']
            
            for _, rec in strategy_recs.iterrows():
                stock_code = rec['stock_code']
                stock_name = rec['stock_name']
                rank = rec['rank']
                
                # 检查是否已有复盘记录
                exists = self.review_cache.check_review_exists(trade_date, strategy_name, stock_code)
                
                # 获取推荐当天的收盘价
                recommendation_price = self.review_helper.get_stock_close_price(stock_code, trade_date)
                if recommendation_price is None:
                    continue  # 跳过没有推荐价的数据
                
                # 计算每日评分
                daily_data = self.review_helper.calculate_daily_scores(
                    stock_code, trade_date, recommendation_price, days
                )
                
                # 保存到数据库
                self.review_cache.save_review_summary(
                    recommendation_date=trade_date,
                    strategy_name=strategy_name,
                    strategy_type=strategy_type,
                    stock_code=stock_code,
                    stock_name=stock_name,
                    recommendation_price=recommendation_price,
                    rank=rank,
                    daily_prices=daily_data['daily_prices'],
                    daily_scores=daily_data['daily_scores'],
                    average_score=daily_data['average_score'],
                    total_score=daily_data['total_score'],
                    valid_days=daily_data['valid_days']
                )
                
                if exists:
                    updated_count += 1
                else:
                    new_count += 1
        
        if new_count > 0 or updated_count > 0:
            print(f"  日期 {trade_date}: 新增 {new_count} 条，更新 {updated_count} 条")
            return (new_count, updated_count)
        
        return None
    
    def fill_missing_reviews(self, days: int = 10):
        """
        补齐缺失的复盘数据
        Args:
            days: 复盘天数
        """
        print("\n" + "=" * 60)
        print("【补齐缺失复盘数据】")
        print("=" * 60)
        
        # 获取前N个交易日
        today = datetime.now().strftime('%Y%m%d')
        trading_dates = self._get_trading_dates_before(today, days)
        
        from data.recommendation_cache import RecommendationCache
        recommendation_cache = RecommendationCache(self.cache_manager)
        
        total_new = 0
        total_updated = 0
        
        for trade_date in trading_dates:
            # 获取推荐结果
            recommendations = recommendation_cache.get_recommendations(trade_date)
            if recommendations is None or recommendations.empty:
                continue
            
            # 检查哪些需要补齐
            for _, rec in recommendations.iterrows():
                strategy_name = rec['strategy_name']
                stock_code = rec['stock_code']
                
                # 检查是否存在
                exists = self.review_cache.check_review_exists(trade_date, strategy_name, stock_code)
                
                if not exists:
                    # 需要补齐
                    result = self.review_single_date(trade_date, days)
                    if result:
                        new_count, updated_count = result
                        total_new += new_count
                        total_updated += updated_count
                        break  # 该日期已处理完
        
        print(f"\n补齐完成: 新增 {total_new} 条，更新 {total_updated} 条")
        print("=" * 60)
    
    def _get_trading_dates_before(self, end_date: str, count: int) -> List[str]:
        """
        获取指定日期之前的N个交易日列表
        Args:
            end_date: 结束日期，格式：YYYYMMDD
            count: 交易日数量
        Returns:
            交易日列表（格式：YYYYMMDD），从早到晚排序
        """
        # 标准化日期格式
        end_date = end_date.replace('-', '')
        
        try:
            # 获取交易日历（扩大范围）
            end_date_obj = datetime.strptime(end_date, '%Y%m%d')
            start_date_obj = end_date_obj - timedelta(days=count * 2)  # 扩大范围确保有足够交易日
            start_date = start_date_obj.strftime('%Y%m%d')
            
            trade_cal = self.data_fetcher.get_trade_calendar(
                start_date=start_date,
                end_date=end_date,
                force_refresh=False
            )
            
            if trade_cal is None or trade_cal.empty:
                return []
            
            # 筛选交易日（小于等于结束日期）
            trade_cal['cal_date'] = trade_cal['cal_date'].astype(str).str.replace('-', '')
            trading_days = trade_cal[
                (trade_cal['cal_date'] <= end_date) & 
                (trade_cal['is_open'] == 1)
            ]['cal_date'].tolist()
            
            # 取最后N个交易日
            return sorted(trading_days)[-count:] if len(trading_days) >= count else sorted(trading_days)
            
        except Exception as e:
            print(f"获取交易日列表失败: {e}")
            return []

