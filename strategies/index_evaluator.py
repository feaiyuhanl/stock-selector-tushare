"""
指数权重策略评估器：单只股票评估逻辑
"""
from typing import Dict, Optional
from scorers.index_weight_scorer import IndexWeightScorer


class IndexEvaluator:
    """指数权重策略评估器"""
    
    def __init__(self, scorer, index_codes, multi_index_bonus):
        """
        初始化评估器
        Args:
            scorer: 指数权重评分器
            index_codes: 要追踪的指数代码列表
            multi_index_bonus: 多指数加分系数
        """
        self.scorer = scorer
        self.index_codes = index_codes
        self.multi_index_bonus = multi_index_bonus
    
    def calculate_weight_trend_score(
        self,
        index_code: str,
        stock_code: str,
        data_fetcher,
        lookback_days: int
    ) -> Optional[Dict]:
        """
        计算单只股票在指定指数中的权重趋势得分
        Args:
            index_code: 指数代码
            stock_code: 股票代码
            data_fetcher: 数据获取器
            lookback_days: 回看天数
        Returns:
            包含得分和详细信息的字典，如果数据不足返回None
        """
        try:
            # 标准化股票代码
            clean_code = str(stock_code).zfill(6)
            
            # 从cache中计算因子
            factors = data_fetcher.cache_manager.calculate_index_weight_factors(
                index_code=index_code,
                con_code=clean_code,
                lookback_days=lookback_days
            )
            
            if factors is None:
                return None
            
            # 使用scorer计算评分
            result = self.scorer.score(factors)
            
            # 为了保持兼容性，添加一些别名字段
            result['change_rate_score'] = result.get('weight_change_rate_score', 50)
            result['slope_score'] = result.get('trend_slope_score', 50)
            result['absolute_score'] = result.get('weight_absolute_score', 50)
            
            return result
            
        except Exception as e:
            print(f"[错误] 计算权重趋势得分失败 ({index_code}, {stock_code}): {e}")
            return None
    
    def evaluate_stock(self, stock_code: str, stock_name: str = "", 
                      data_fetcher=None, lookback_days: int = None) -> Optional[Dict]:
        """
        评估单只股票在指数中的权重上升趋势
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            data_fetcher: 数据获取器
            lookback_days: 回看天数
        Returns:
            评估结果字典
        """
        try:
            # 获取股票名称
            if not stock_name:
                stock_list = data_fetcher.get_stock_list()
                if stock_list is not None and not stock_list.empty:
                    stock_row = stock_list[stock_list['code'] == str(stock_code).zfill(6)]
                    if not stock_row.empty:
                        stock_name = stock_row.iloc[0].get('name', stock_code)
            
            # 计算该股票在各个指数中的得分
            index_scores = {}
            total_score = 0
            valid_index_count = 0
            
            for index_code in self.index_codes:
                trend_result = self.calculate_weight_trend_score(
                    index_code, stock_code, data_fetcher, lookback_days
                )
                if trend_result is not None:
                    index_scores[index_code] = trend_result
                    total_score += trend_result['score']
                    valid_index_count += 1
            
            if valid_index_count == 0:
                # 该股票不在任何追踪的指数中，或数据不足
                return None
            
            # 计算平均得分
            avg_score = total_score / valid_index_count
            
            # 多指数加分
            if valid_index_count > 1:
                final_score = avg_score * self.multi_index_bonus
            else:
                final_score = avg_score
            
            # 限制得分范围在0-100
            final_score = max(0, min(100, final_score))
            
            # 构建结果字典
            result = {
                'code': str(stock_code).zfill(6),
                'name': stock_name,
                'score': final_score,
                'index_count': valid_index_count,
                'index_scores': index_scores,
            }
            
            # 添加详细信息（用于调试和展示）
            if index_scores:
                # 获取第一个指数的详细信息作为主要信息
                first_index = list(index_scores.keys())[0]
                first_result = index_scores[first_index]
                result.update({
                    'weight_change_rate': first_result['weight_change_rate'],
                    'trend_slope': first_result['trend_slope'],
                    'latest_weight': first_result['latest_weight'],
                    'oldest_weight': first_result['oldest_weight'],
                })
            
            return result
            
        except Exception as e:
            print(f"[错误] 评估股票失败 ({stock_code}): {e}")
            import traceback
            traceback.print_exc()
            return None

