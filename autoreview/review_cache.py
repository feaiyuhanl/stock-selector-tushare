"""
复盘数据缓存管理模块
"""
import pandas as pd
import sqlite3
from typing import Dict, List, Optional
from datetime import datetime


class ReviewCache:
    """复盘汇总数据缓存管理器"""
    
    def __init__(self, cache_manager):
        """
        初始化复盘缓存管理器
        Args:
            cache_manager: CacheManager实例
        """
        self.cache_manager = cache_manager
        self.base = cache_manager  # CacheBase实例
    
    def save_review_summary(
        self,
        recommendation_date: str,
        strategy_name: str,
        strategy_type: str,
        stock_code: str,
        stock_name: str,
        recommendation_price: float,
        rank: int,
        daily_prices: Dict[str, float],
        daily_scores: Dict[str, float],
        average_score: float,
        total_score: float,
        valid_days: int
    ):
        """
        保存或更新复盘汇总记录
        Args:
            recommendation_date: 推荐日期，格式：YYYYMMDD
            strategy_name: 策略名称
            strategy_type: 策略类型
            stock_code: 股票代码
            stock_name: 股票名称
            recommendation_price: 推荐当天的收盘价
            rank: 推荐时的排名
            daily_prices: {日期: 收盘价} 字典，日期格式：YYYYMMDD
            daily_scores: {日期: 评分} 字典，日期格式：YYYYMMDD
            average_score: 平均分
            total_score: 总评分
            valid_days: 有效交易日数
        """
        # 标准化日期格式
        recommendation_date = recommendation_date.replace('-', '')
        stock_code = self.base._normalize_stock_code(stock_code)
        
        try:
            # 准备日期列表（按顺序）
            dates = sorted(daily_prices.keys()) if daily_prices else []
            
            # 准备数据（最多10个交易日）
            day_data = {}
            for i in range(1, 11):
                if i - 1 < len(dates):
                    date = dates[i - 1]
                    day_data[f'day{i}_price'] = daily_prices.get(date)
                    day_data[f'day{i}_score'] = daily_scores.get(date)
                else:
                    day_data[f'day{i}_price'] = None
                    day_data[f'day{i}_score'] = None
            
            with self.base._get_db_connection(timeout=30.0) as conn:
                cursor = conn.cursor()
                
                # 使用 INSERT OR REPLACE 更新记录
                cursor.execute('''
                    INSERT OR REPLACE INTO review_summary
                    (recommendation_date, strategy_name, strategy_type, stock_code, stock_name,
                     recommendation_price, rank,
                     day1_price, day1_score,
                     day2_price, day2_score,
                     day3_price, day3_score,
                     day4_price, day4_score,
                     day5_price, day5_score,
                     day6_price, day6_score,
                     day7_price, day7_score,
                     day8_price, day8_score,
                     day9_price, day9_score,
                     day10_price, day10_score,
                     average_score, total_score, valid_days, last_update_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?)
                ''', (
                    recommendation_date, strategy_name, strategy_type, stock_code, stock_name,
                    recommendation_price, rank,
                    day_data['day1_price'], day_data['day1_score'],
                    day_data['day2_price'], day_data['day2_score'],
                    day_data['day3_price'], day_data['day3_score'],
                    day_data['day4_price'], day_data['day4_score'],
                    day_data['day5_price'], day_data['day5_score'],
                    day_data['day6_price'], day_data['day6_score'],
                    day_data['day7_price'], day_data['day7_score'],
                    day_data['day8_price'], day_data['day8_score'],
                    day_data['day9_price'], day_data['day9_score'],
                    day_data['day10_price'], day_data['day10_score'],
                    average_score, total_score, valid_days,
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ))
                
                conn.commit()
                
        except Exception as e:
            print(f"保存复盘汇总记录失败 ({recommendation_date}, {stock_code}): {e}")
            import traceback
            traceback.print_exc()
    
    def get_review_summary(
        self,
        recommendation_date: str = None,
        strategy_name: str = None,
        strategy_type: str = None,
        stock_code: str = None
    ) -> Optional[pd.DataFrame]:
        """
        获取复盘汇总记录
        Args:
            recommendation_date: 推荐日期，格式：YYYYMMDD，如果为None则返回所有日期
            strategy_name: 策略名称，如果为None则返回所有策略
            strategy_type: 策略类型，如果为None则返回所有类型
            stock_code: 股票代码，如果为None则返回所有股票
        Returns:
            复盘汇总DataFrame
        """
        try:
            with sqlite3.connect(self.base.db_path) as conn:
                query = '''
                    SELECT recommendation_date, strategy_name, strategy_type, stock_code, stock_name,
                           recommendation_price, rank,
                           day1_price, day1_score,
                           day2_price, day2_score,
                           day3_price, day3_score,
                           day4_price, day4_score,
                           day5_price, day5_score,
                           day6_price, day6_score,
                           day7_price, day7_score,
                           day8_price, day8_score,
                           day9_price, day9_score,
                           day10_price, day10_score,
                           average_score, total_score, valid_days, last_update_time
                    FROM review_summary
                    WHERE 1=1
                '''
                params = []
                
                if recommendation_date:
                    recommendation_date = recommendation_date.replace('-', '')
                    query += ' AND recommendation_date = ?'
                    params.append(recommendation_date)
                
                if strategy_name:
                    query += ' AND strategy_name = ?'
                    params.append(strategy_name)
                
                if strategy_type:
                    query += ' AND strategy_type = ?'
                    params.append(strategy_type)
                
                if stock_code:
                    stock_code = self.base._normalize_stock_code(stock_code)
                    query += ' AND stock_code = ?'
                    params.append(stock_code)
                
                query += ' ORDER BY recommendation_date DESC, strategy_name, rank'
                
                df = pd.read_sql_query(query, conn, params=params)
                
                return df if not df.empty else None
                
        except Exception as e:
            print(f"读取复盘汇总记录失败: {e}")
            return None
    
    def check_review_exists(
        self,
        recommendation_date: str,
        strategy_name: str,
        stock_code: str
    ) -> bool:
        """
        检查复盘记录是否存在
        Args:
            recommendation_date: 推荐日期，格式：YYYYMMDD
            strategy_name: 策略名称
            stock_code: 股票代码
        Returns:
            是否存在
        """
        recommendation_date = recommendation_date.replace('-', '')
        stock_code = self.base._normalize_stock_code(stock_code)
        
        try:
            with sqlite3.connect(self.base.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM review_summary
                    WHERE recommendation_date = ? AND strategy_name = ? AND stock_code = ?
                ''', (recommendation_date, strategy_name, stock_code))
                count = cursor.fetchone()[0]
                return count > 0
        except Exception as e:
            return False

