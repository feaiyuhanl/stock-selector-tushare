"""
复盘工具函数模块
"""
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from data.fetcher_base import FetcherBase
from data.cache_manager import CacheManager


def calculate_performance_score(base_price: float, current_price: float) -> float:
    """
    计算表现评分
    Args:
        base_price: 基准价格（推荐当天的收盘价）
        current_price: 当前价格
    Returns:
        评分（0-100分）
    """
    if base_price is None or current_price is None or base_price <= 0:
        return 60.0
    
    # 计算累计涨幅
    change_rate = (current_price - base_price) / base_price
    
    # 打分规则：
    # - 如果累计涨幅 = 0: 60分
    # - 如果累计涨幅 > 0: 60 + min(40, 累计涨幅 * 100)  （最高100分）
    # - 如果累计涨幅 < 0: 60 + max(-60, 累计涨幅 * 100)  （最低0分）
    
    if change_rate == 0:
        return 60.0
    elif change_rate > 0:
        score = 60 + min(40, change_rate * 100)
        return round(min(100, score), 2)
    else:
        score = 60 + max(-60, change_rate * 100)
        return round(max(0, score), 2)


class ReviewHelper:
    """复盘辅助工具类"""
    
    def __init__(self, data_fetcher: FetcherBase, cache_manager: CacheManager):
        self.data_fetcher = data_fetcher
        self.cache_manager = cache_manager
    
    def get_trading_dates_after(self, start_date: str, days: int) -> List[str]:
        """
        获取指定日期之后的N个交易日列表
        Args:
            start_date: 起始日期，格式：YYYYMMDD
            days: 交易日数量
        Returns:
            交易日列表（格式：YYYYMMDD）
        """
        # 标准化日期格式
        start_date = start_date.replace('-', '')
        
        try:
            # 获取交易日历
            end_date = (datetime.now() + timedelta(days=days * 2)).strftime('%Y%m%d')  # 扩大范围确保有足够交易日
            trade_cal = self.data_fetcher.get_trade_calendar(start_date=start_date, end_date=end_date, force_refresh=False)
            
            if trade_cal is None or trade_cal.empty:
                return []
            
            # 筛选交易日
            trade_cal['cal_date'] = trade_cal['cal_date'].astype(str).str.replace('-', '')
            trading_days = trade_cal[
                (trade_cal['cal_date'] > start_date) & 
                (trade_cal['is_open'] == 1)
            ]['cal_date'].tolist()
            
            # 取前N个交易日
            return sorted(trading_days)[:days]
            
        except Exception as e:
            print(f"获取交易日列表失败: {e}")
            return []
    
    def get_stock_close_price(self, stock_code: str, trade_date: str) -> Optional[float]:
        """
        获取股票在指定日期的收盘价
        Args:
            stock_code: 股票代码
            trade_date: 交易日期，格式：YYYYMMDD
        Returns:
            收盘价，如果不存在则返回None
        """
        try:
            stock_code = self.data_fetcher._format_stock_code(stock_code)
            trade_date_str = trade_date.replace('-', '')
            trade_date_obj = datetime.strptime(trade_date_str, '%Y%m%d')
            date_str = trade_date_obj.strftime('%Y-%m-%d')
            
            # 从K线数据获取
            kline_data = self.cache_manager.get_kline(stock_code, 'stock', 'daily', force_refresh=False)
            if kline_data is not None and not kline_data.empty:
                kline_data['date'] = pd.to_datetime(kline_data['date'])
                target_date = pd.to_datetime(date_str)
                match = kline_data[kline_data['date'].dt.date == target_date.date()]
                if not match.empty:
                    return float(match.iloc[0]['close'])
            
            return None
            
        except Exception as e:
            return None
    
    def calculate_daily_scores(
        self,
        stock_code: str,
        recommendation_date: str,
        recommendation_price: float,
        days: int = 10
    ) -> Dict:
        """
        计算N个交易日的每日评分
        Args:
            stock_code: 股票代码
            recommendation_date: 推荐日期，格式：YYYYMMDD
            recommendation_price: 推荐当天的收盘价
            days: 复盘天数
        Returns:
            字典包含：
            - daily_prices: {日期: 收盘价}
            - daily_scores: {日期: 评分}
            - average_score: 平均分
            - total_score: 总评分（最后一天）
            - valid_days: 有效交易日数
        """
        trading_dates = self.get_trading_dates_after(recommendation_date, days)
        
        daily_prices = {}
        daily_scores = {}
        
        for date in trading_dates:
            price = self.get_stock_close_price(stock_code, date)
            if price is not None:
                daily_prices[date] = price
                daily_scores[date] = calculate_performance_score(recommendation_price, price)
        
        # 计算平均分和总评分
        valid_days = len(daily_scores)
        if valid_days > 0:
            scores_list = list(daily_scores.values())
            average_score = round(sum(scores_list) / valid_days, 2)
            total_score = scores_list[-1] if scores_list else None
        else:
            average_score = None
            total_score = None
        
        return {
            'daily_prices': daily_prices,
            'daily_scores': daily_scores,
            'average_score': average_score,
            'total_score': total_score,
            'valid_days': valid_days
        }
    
    def review_single_date(
        self,
        trade_date: str,
        days: int = 10,
        strategy_name: str = None
    ) -> Optional[pd.DataFrame]:
        """
        复盘单个日期的推荐结果（命令行使用）
        Args:
            trade_date: 推荐日期，格式：YYYYMMDD
            days: 复盘天数
            strategy_name: 策略名称，如果为None则复盘所有策略
        Returns:
            复盘结果DataFrame
        """
        from data.recommendation_cache import RecommendationCache
        recommendation_cache = RecommendationCache(self.cache_manager)
        
        # 获取推荐结果
        recommendations = recommendation_cache.get_recommendations(trade_date, strategy_name)
        
        if recommendations is None or recommendations.empty:
            print(f"未找到日期 {trade_date} 的推荐结果")
            return None
        
        # 对每只股票进行复盘
        review_results = []
        
        for strategy_name in recommendations['strategy_name'].unique():
            strategy_recs = recommendations[recommendations['strategy_name'] == strategy_name]
            
            print(f"\n【复盘】策略: {strategy_name}, 推荐日期: {trade_date}")
            print(f"  推荐股票数: {len(strategy_recs)}")
            
            for _, rec in strategy_recs.iterrows():
                stock_code = rec['stock_code']
                stock_name = rec['stock_name']
                rank = rec['rank']
                score = rec['score']
                
                # 获取推荐当天的收盘价
                recommendation_price = self.get_stock_close_price(stock_code, trade_date)
                if recommendation_price is None:
                    print(f"  ⚠ {stock_code} {stock_name}: 未找到推荐当天的收盘价，跳过")
                    continue
                
                # 计算每日评分
                daily_data = self.calculate_daily_scores(
                    stock_code, trade_date, recommendation_price, days
                )
                
                # 构建结果
                result = {
                    'code': stock_code,
                    'name': stock_name,
                    'rank': rank,
                    'recommendation_score': score,
                    'recommendation_price': recommendation_price,
                    'average_score': daily_data['average_score'],
                    'total_score': daily_data['total_score'],
                    'valid_days': daily_data['valid_days']
                }
                
                # 添加每日评分
                for i in range(1, days + 1):
                    date_key = f'day{i}'
                    if i <= len(daily_data['daily_scores']):
                        dates = sorted(daily_data['daily_scores'].keys())
                        if i - 1 < len(dates):
                            date = dates[i - 1]
                            result[f'day{i}_price'] = daily_data['daily_prices'][date]
                            result[f'day{i}_score'] = daily_data['daily_scores'][date]
                        else:
                            result[f'day{i}_price'] = None
                            result[f'day{i}_score'] = None
                    else:
                        result[f'day{i}_price'] = None
                        result[f'day{i}_score'] = None
                
                review_results.append(result)
        
        if not review_results:
            return None
        
        df = pd.DataFrame(review_results)
        return df
    
    def generate_review_report(self, review_data: pd.DataFrame, trade_date: str, days: int) -> str:
        """
        生成复盘报告
        Args:
            review_data: 复盘结果DataFrame
            trade_date: 推荐日期
            days: 复盘天数
        Returns:
            报告文本
        """
        if review_data is None or review_data.empty:
            return "无复盘数据"
        
        lines = []
        lines.append("=" * 80)
        lines.append(f"【复盘报告】")
        lines.append(f"推荐日期: {trade_date}")
        lines.append(f"复盘天数: {days}个交易日")
        lines.append("=" * 80)
        
        # 构建表头
        header = ["排名", "代码", "名称", "推荐价"]
        for i in range(1, days + 1):
            header.append(f"第{i}日")
        header.extend(["平均分", "总评分"])
        lines.append(" | ".join([f"{h:^10}" for h in header]))
        lines.append("-" * 80)
        
        # 添加数据行
        for _, row in review_data.iterrows():
            row_data = [
                str(int(row.get('rank', 0))),
                str(row.get('code', '')),
                str(row.get('name', ''))[:8],
                f"{row.get('recommendation_price', 0):.2f}" if row.get('recommendation_price') else "N/A"
            ]
            
            for i in range(1, days + 1):
                score = row.get(f'day{i}_score')
                if score is not None:
                    row_data.append(f"{score:.1f}")
                else:
                    row_data.append("N/A")
            
            row_data.append(f"{row.get('average_score', 0):.2f}" if row.get('average_score') else "N/A")
            row_data.append(f"{row.get('total_score', 0):.2f}" if row.get('total_score') else "N/A")
            
            lines.append(" | ".join([f"{d:^10}" for d in row_data]))
        
        # 统计信息
        valid_scores = review_data['total_score'].dropna()
        if len(valid_scores) > 0:
            lines.append("-" * 80)
            lines.append(f"【统计信息】")
            lines.append(f"  总股票数: {len(review_data)}")
            lines.append(f"  平均总评分: {valid_scores.mean():.2f}")
            if not valid_scores.empty:
                lines.append(f"  最高评分: {valid_scores.max():.2f} ({review_data.loc[valid_scores.idxmax(), 'code']})")
                lines.append(f"  最低评分: {valid_scores.min():.2f} ({review_data.loc[valid_scores.idxmin(), 'code']})")
        
        lines.append("=" * 80)
        
        return "\n".join(lines)

