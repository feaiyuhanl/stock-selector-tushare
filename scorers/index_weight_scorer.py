"""
指数权重评分模块
"""
from typing import Dict, Optional
import config


class IndexWeightScorer:
    """指数权重评分器"""
    
    def __init__(self, weights: Dict[str, float] = None):
        """
        初始化指数权重评分器
        Args:
            weights: 子维度权重字典，如果为None则使用config中的默认权重
        """
        if weights is None:
            self.weights = config.INDEX_WEIGHT_CONFIG['score_weights']
        else:
            self.weights = weights
    
    def score(self, factors: Dict) -> dict:
        """
        计算指数权重综合得分和详细指标
        Args:
            factors: 因子值字典，包含：
                - weight_change_rate: 权重变化率
                - trend_slope: 趋势斜率
                - weight_absolute: 权重绝对值
        Returns:
            字典包含：score（综合得分）以及各项指标得分
        """
        if factors is None:
            return {
                'score': 50,
                'weight_change_rate': None,
                'trend_slope': None,
                'weight_absolute': None,
                'weight_change_rate_score': 50,
                'trend_slope_score': 50,
                'weight_absolute_score': 50
            }
        
        scores = {}
        
        # 提取因子值
        weight_change_rate = factors.get('weight_change_rate')
        trend_slope = factors.get('trend_slope')
        weight_absolute = factors.get('weight_absolute')
        
        # 1. 权重变化率得分
        if weight_change_rate is not None:
            if weight_change_rate >= 0.5:
                scores['weight_change_rate'] = 100
            elif weight_change_rate >= 0.3:
                scores['weight_change_rate'] = 80
            elif weight_change_rate >= 0.1:
                scores['weight_change_rate'] = 60
            elif weight_change_rate >= 0:
                scores['weight_change_rate'] = 40 + weight_change_rate * 200  # 0-0.1映射到40-60
            else:
                scores['weight_change_rate'] = max(0, 40 + weight_change_rate * 400)  # 负值映射到0-40
        else:
            scores['weight_change_rate'] = 50
        
        # 2. 趋势斜率得分
        if trend_slope is not None:
            # 斜率越大（正数），得分越高
            if trend_slope >= 0.01:
                scores['trend_slope'] = 100
            elif trend_slope >= 0.005:
                scores['trend_slope'] = 80
            elif trend_slope >= 0.001:
                scores['trend_slope'] = 60
            elif trend_slope >= 0:
                scores['trend_slope'] = 40 + trend_slope * 20000  # 0-0.001映射到40-60
            else:
                scores['trend_slope'] = max(0, 40 + trend_slope * 40000)  # 负值映射到0-40
        else:
            scores['trend_slope'] = 50
        
        # 3. 权重绝对值得分
        if weight_absolute is not None:
            # 权重越大，基础得分越高（但权重变化趋势更重要）
            if weight_absolute >= 2.0:
                scores['weight_absolute'] = 100
            elif weight_absolute >= 1.0:
                scores['weight_absolute'] = 80
            elif weight_absolute >= 0.5:
                scores['weight_absolute'] = 60
            elif weight_absolute >= 0.1:
                scores['weight_absolute'] = 40
            else:
                scores['weight_absolute'] = 20
        else:
            scores['weight_absolute'] = 50
        
        # 计算加权总分
        total_score = (
            scores.get('weight_change_rate', 50) * self.weights.get('weight_change_rate', 0.5) +
            scores.get('trend_slope', 50) * self.weights.get('trend_slope', 0.3) +
            scores.get('weight_absolute', 50) * self.weights.get('weight_absolute', 0.2)
        )
        total_score = min(100, max(0, total_score))
        
        return {
            'score': total_score,
            'weight_change_rate': weight_change_rate,
            'trend_slope': trend_slope,
            'weight_absolute': weight_absolute,
            'weight_change_rate_score': scores.get('weight_change_rate', 50),
            'trend_slope_score': scores.get('trend_slope', 50),
            'weight_absolute_score': scores.get('weight_absolute', 50),
            'oldest_weight': factors.get('oldest_weight'),
            'latest_weight': factors.get('latest_weight'),
            'data_points': factors.get('data_points')
        }

