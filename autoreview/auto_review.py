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
        
        # 前 N 个交易日不含当日（当日无后续数据，只做推荐保存）
        from data.utils import get_analysis_date
        end_date = (get_analysis_date() - timedelta(days=1)).strftime('%Y%m%d')
        trading_dates = self._get_trading_dates_before(end_date, days)
        
        # 只处理 >= review_start_date 的日期（有推荐结果才参与更新）
        start = (config.AUTO_REVIEW_CONFIG.get('review_start_date') or '').strip() or None
        if start:
            trading_dates = [d for d in trading_dates if d >= start]
        
        if not trading_dates:
            print("未找到过去 N 个交易日数据，仅处理当日推荐。")
        trade_date_today = get_analysis_date().strftime('%Y%m%d')
        # 复盘范围：当日 + 过去 N 个交易日，确保 strategy_recommendations 中所有推荐都能生成 review_summary
        dates_to_process = [trade_date_today] + trading_dates
        if start:
            dates_to_process = [d for d in dates_to_process if d >= start]
        
        total_new = 0
        total_updated = 0
        processed_dates = 0
        from data.recommendation_cache import RecommendationCache
        rec_cache = RecommendationCache(self.cache_manager)
        
        for trade_date in dates_to_process:
            recommendations = rec_cache.get_recommendations(trade_date)
            if recommendations is None or recommendations.empty:
                continue
            new_count = 0
            updated_count = 0
            is_today = (trade_date == trade_date_today)
            for strategy_name in recommendations['strategy_name'].unique():
                strategy_recs = recommendations[recommendations['strategy_name'] == strategy_name]
                strategy_type = strategy_recs.iloc[0]['strategy_type']
                for _, rec in strategy_recs.iterrows():
                    stock_code = rec['stock_code']
                    stock_name = rec['stock_name']
                    rank = rec['rank']
                    
                    # 检查记录是否已存在
                    existing = self.review_cache.get_existing_review(trade_date, strategy_name, stock_code)
                    
                    if existing is None:
                        # 新记录：创建
                        recommendation_price = self.review_helper.get_stock_close_price(stock_code, trade_date)
                        if is_today:
                            # 当日占位：无后续 10 日数据；recommendation_price 为 None 也写入，保证有推荐即有复盘
                            self.review_cache.save_review_summary(
                                recommendation_date=trade_date,
                                strategy_name=strategy_name,
                                strategy_type=strategy_type,
                                stock_code=stock_code,
                                stock_name=stock_name,
                                recommendation_price=recommendation_price,
                                rank=rank,
                                daily_prices={},
                                daily_scores={},
                                average_score=None,
                                total_score=None,
                                valid_days=0
                            )
                            new_count += 1
                        else:
                            if recommendation_price is not None:
                                daily_data = self.review_helper.calculate_daily_scores(
                                    stock_code, trade_date, recommendation_price, days
                                )
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
                                new_count += 1
                            else:
                                # 历史日占位：无推荐日收盘价也写入，保证有推荐即有复盘
                                self.review_cache.save_review_summary(
                                    recommendation_date=trade_date,
                                    strategy_name=strategy_name,
                                    strategy_type=strategy_type,
                                    stock_code=stock_code,
                                    stock_name=stock_name,
                                    recommendation_price=None,
                                    rank=rank,
                                    daily_prices={},
                                    daily_scores={},
                                    average_score=None,
                                    total_score=None,
                                    valid_days=0
                                )
                                new_count += 1
                    else:
                        # 已存在记录：检查是否需要更新
                        updated_recommendation_price = existing['recommendation_price']
                        should_update = False
                        
                        # 1. 如果 recommendation_price 为空，尝试更新
                        if existing['recommendation_price'] is None:
                            new_price = self.review_helper.get_stock_close_price(stock_code, trade_date)
                            if new_price is not None:
                                updated_recommendation_price = new_price
                                should_update = True
                        
                        # 2. 对于历史推荐（非当日），重新计算所有可用的 day1-day10 数据
                        if not is_today:
                            base_price = updated_recommendation_price or self.review_helper.get_stock_close_price(stock_code, trade_date)
                            
                            if base_price is not None:
                                # 重新计算所有可用的交易日数据
                                daily_data = self.review_helper.calculate_daily_scores(
                                    stock_code, trade_date, base_price, days
                                )
                                
                                # 检查是否有新的数据需要更新
                                # 如果 recommendation_price 被更新，或者新的有效天数更多，则更新
                                existing_valid_days = existing.get('valid_days', 0)
                                new_valid_days = daily_data.get('valid_days', 0)
                                
                                if should_update or new_valid_days > existing_valid_days:
                                    self.review_cache.save_review_summary(
                                        recommendation_date=trade_date,
                                        strategy_name=strategy_name,
                                        strategy_type=strategy_type,
                                        stock_code=stock_code,
                                        stock_name=stock_name,
                                        recommendation_price=updated_recommendation_price,
                                        rank=rank,
                                        daily_prices=daily_data['daily_prices'],
                                        daily_scores=daily_data['daily_scores'],
                                        average_score=daily_data['average_score'],
                                        total_score=daily_data['total_score'],
                                        valid_days=daily_data['valid_days']
                                    )
                                    updated_count += 1
                            elif should_update:
                                # 只更新了 recommendation_price，但无法计算 daily_data，保留现有的 daily 数据
                                # 从现有记录中提取 daily_prices 和 daily_scores
                                existing_daily_prices = {}
                                existing_daily_scores = {}
                                trading_dates_after = self.review_helper.get_trading_dates_after(trade_date, days)
                                for j in range(1, 11):
                                    if existing.get(f'day{j}_price') is not None and j - 1 < len(trading_dates_after):
                                        date_key = trading_dates_after[j - 1]
                                        existing_daily_prices[date_key] = existing[f'day{j}_price']
                                        if existing.get(f'day{j}_score') is not None:
                                            existing_daily_scores[date_key] = existing[f'day{j}_score']
                                
                                # 如果有 daily_prices，重新计算评分
                                if existing_daily_prices and updated_recommendation_price:
                                    from .review_helper import calculate_performance_score
                                    recalculated_scores = {}
                                    for date, price in existing_daily_prices.items():
                                        recalculated_scores[date] = calculate_performance_score(updated_recommendation_price, price)
                                    
                                    if recalculated_scores:
                                        scores_list = list(recalculated_scores.values())
                                        updated_average_score = round(sum(scores_list) / len(scores_list), 2)
                                        updated_total_score = scores_list[-1] if scores_list else None
                                        updated_valid_days = len(recalculated_scores)
                                    else:
                                        updated_average_score = existing.get('average_score')
                                        updated_total_score = existing.get('total_score')
                                        updated_valid_days = existing.get('valid_days', 0)
                                else:
                                    updated_average_score = existing.get('average_score')
                                    updated_total_score = existing.get('total_score')
                                    updated_valid_days = existing.get('valid_days', 0)
                                
                                self.review_cache.save_review_summary(
                                    recommendation_date=trade_date,
                                    strategy_name=strategy_name,
                                    strategy_type=strategy_type,
                                    stock_code=stock_code,
                                    stock_name=stock_name,
                                    recommendation_price=updated_recommendation_price,
                                    rank=rank,
                                    daily_prices=existing_daily_prices,
                                    daily_scores=existing_daily_scores,
                                    average_score=updated_average_score,
                                    total_score=updated_total_score,
                                    valid_days=updated_valid_days
                                )
                                updated_count += 1
                        elif should_update:
                            # 当日推荐：只更新 recommendation_price，保留其他字段
                            self.review_cache.save_review_summary(
                                recommendation_date=trade_date,
                                strategy_name=strategy_name,
                                strategy_type=strategy_type,
                                stock_code=stock_code,
                                stock_name=stock_name,
                                recommendation_price=updated_recommendation_price,
                                rank=rank,
                                daily_prices={},
                                daily_scores={},
                                average_score=None,
                                total_score=None,
                                valid_days=0
                            )
                            updated_count += 1
            
            if new_count > 0 or updated_count > 0:
                processed_dates += 1
                total_new += new_count
                total_updated += updated_count
                label = "当日/占位" if is_today else "历史"
                update_info = f"，更新 {updated_count} 条" if updated_count > 0 else ""
                print(f"  日期 {trade_date} ({label}): 新增 {new_count} 条{update_info}")
        
        print("\n" + "=" * 60)
        print("【自动复盘完成】")
        print(f"  处理日期数: {processed_dates}/{len(dates_to_process)}")
        print(f"  新增记录: {total_new} 条")
        print(f"  更新记录: {total_updated} 条")
        if processed_dates == 0 and total_new + total_updated == 0:
            print("[自动复盘] 过去 {} 个交易日无历史推荐数据，本次无可复盘内容。请连续多日运行选股以在 strategy_recommendations 中积累数据，后续复盘与飞书同步才会有结果。".format(days))
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
                
                # 已有复盘结果则跳过，不重复复盘
                if self.review_cache.check_review_exists(trade_date, strategy_name, stock_code):
                    continue
                
                recommendation_price = self.review_helper.get_stock_close_price(stock_code, trade_date)
                if recommendation_price is None:
                    continue
                
                daily_data = self.review_helper.calculate_daily_scores(
                    stock_code, trade_date, recommendation_price, days
                )
                
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
                new_count += 1
        
        if new_count > 0 or updated_count > 0:
            print(f"  日期 {trade_date}: 新增 {new_count} 条，更新 {updated_count} 条")
            return (new_count, updated_count)
        
        return None
    
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

