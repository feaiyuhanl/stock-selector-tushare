"""
成交量评分模块
"""
import numpy as np
import pandas as pd
from typing import Dict, Optional
import config


class VolumeScorer:
    """成交量评分器"""
    
    def __init__(self):
        self.weights = config.VOLUME_WEIGHTS
    
    def score(self, kline_data: pd.DataFrame, current_volume: float = None) -> float:
        """
        计算成交量综合得分
        Args:
            kline_data: K线数据（包含成交量）
            current_volume: 当前成交量（可选）
        Returns:
            综合得分 0-100
        """
        if kline_data is None or kline_data.empty:
            return 50
        
        scores = {}
        volumes = kline_data['volume'].values
        
        if len(volumes) < 5:
            return 50
        
        # 1. 量比评分（当前成交量/平均成交量）
        if current_volume is None and len(volumes) > 0:
            current_volume = volumes[-1]
        
        avg_volume = np.mean(volumes[:-1]) if len(volumes) > 1 else volumes[0]
        
        if avg_volume > 0:
            volume_ratio = current_volume / avg_volume
            # 量比在1.5-3之间较好，过高可能异常
            if 1.5 <= volume_ratio <= 3:
                scores['volume_ratio'] = 100
            elif 1.2 <= volume_ratio < 1.5 or 3 < volume_ratio <= 4:
                scores['volume_ratio'] = 80
            elif 1.0 <= volume_ratio < 1.2 or 4 < volume_ratio <= 5:
                scores['volume_ratio'] = 60
            elif volume_ratio < 1.0:
                scores['volume_ratio'] = max(0, 40 + volume_ratio * 20)
            else:
                scores['volume_ratio'] = max(0, 60 - (volume_ratio - 5) * 5)
        else:
            scores['volume_ratio'] = 50
        
        # 2. 换手率评分（适度换手较好）
        if 'turnover_rate' in kline_data.columns:
            turnover_rates = kline_data['turnover_rate'].values
            current_turnover = turnover_rates[-1] if len(turnover_rates) > 0 else 0
            
            # 换手率在2%-10%之间较好
            if 2 <= current_turnover <= 10:
                scores['turnover_rate'] = 100
            elif 1 <= current_turnover < 2 or 10 < current_turnover <= 15:
                scores['turnover_rate'] = 80
            elif 0.5 <= current_turnover < 1 or 15 < current_turnover <= 20:
                scores['turnover_rate'] = 60
            else:
                scores['turnover_rate'] = max(0, 40)
        else:
            scores['turnover_rate'] = 50
        
        # 3. 成交量趋势评分（上升趋势较好）
        if len(volumes) >= 10:
            # 计算短期和长期均量
            short_avg = np.mean(volumes[-5:])
            long_avg = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes[:-5])
            
            if long_avg > 0:
                trend_ratio = short_avg / long_avg
                # 短期均量大于长期均量表示放量趋势
                if trend_ratio >= 1.2:
                    scores['volume_trend'] = 100
                elif trend_ratio >= 1.1:
                    scores['volume_trend'] = 85
                elif trend_ratio >= 1.0:
                    scores['volume_trend'] = 70
                elif trend_ratio >= 0.9:
                    scores['volume_trend'] = 50
                else:
                    scores['volume_trend'] = max(0, 30)
            else:
                scores['volume_trend'] = 50
        else:
            scores['volume_trend'] = 50
        
        # 计算加权总分
        total_score = sum(scores.get(key, 50) * self.weights.get(key, 0) 
                         for key in self.weights.keys())
        
        return min(100, max(0, total_score))

