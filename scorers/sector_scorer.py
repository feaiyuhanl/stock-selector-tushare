"""
关联板块走势评分模块
"""
import numpy as np
import pandas as pd
from typing import List, Optional, Dict
import config


class SectorScorer:
    """板块走势评分器"""
    
    def __init__(self):
        self.weights = config.SECTOR_CONCEPT_WEIGHTS
    
    def score(self, sector_kline_list: List[pd.DataFrame], stock_kline: pd.DataFrame) -> float:
        """
        计算板块走势综合得分
        Args:
            sector_kline_list: 板块K线数据列表
            stock_kline: 股票K线数据
        Returns:
            综合得分 0-100
        """
        if not sector_kline_list or stock_kline is None or stock_kline.empty:
            return 50
        
        scores = []
        
        for sector_kline in sector_kline_list:
            if sector_kline is None or sector_kline.empty:
                continue
            
            # 确保有收盘价列
            if '收盘' in sector_kline.columns:
                closes = sector_kline['收盘'].values
            elif 'close' in sector_kline.columns:
                closes = sector_kline['close'].values
            else:
                continue
            
            if len(closes) < 5:
                continue
            
            sector_scores = {}
            
            # 1. 板块趋势评分
            if len(closes) >= 20:
                short_ma = np.mean(closes[-5:])
                long_ma = np.mean(closes[-20:])
                
                if long_ma > 0:
                    trend_ratio = short_ma / long_ma
                    if trend_ratio >= 1.05:
                        sector_scores['sector_trend'] = 100
                    elif trend_ratio >= 1.02:
                        sector_scores['sector_trend'] = 85
                    elif trend_ratio >= 1.0:
                        sector_scores['sector_trend'] = 70
                    else:
                        sector_scores['sector_trend'] = max(0, 50)
                else:
                    sector_scores['sector_trend'] = 50
            else:
                recent_change = (closes[-1] - closes[0]) / closes[0] if len(closes) > 0 else 0
                if recent_change > 0.05:
                    sector_scores['sector_trend'] = 85
                elif recent_change > 0:
                    sector_scores['sector_trend'] = 70
                else:
                    sector_scores['sector_trend'] = 50
            
            # 2. 相对强度评分（股票相对板块的表现）
            if stock_kline is not None and not stock_kline.empty:
                stock_closes = stock_kline['close'].values
                if len(stock_closes) >= 5 and len(closes) >= 5:
                    # 计算股票和板块的近期涨跌幅
                    stock_change = (stock_closes[-1] - stock_closes[-min(5, len(stock_closes))]) / stock_closes[-min(5, len(stock_closes))]
                    sector_change = (closes[-1] - closes[-min(5, len(closes))]) / closes[-min(5, len(closes))]
                    
                    relative_strength = stock_change - sector_change
                    
                    if relative_strength > 0.05:
                        sector_scores['relative_strength'] = 100
                    elif relative_strength > 0.02:
                        sector_scores['relative_strength'] = 85
                    elif relative_strength > 0:
                        sector_scores['relative_strength'] = 70
                    elif relative_strength > -0.02:
                        sector_scores['relative_strength'] = 50
                    else:
                        sector_scores['relative_strength'] = max(0, 30)
                else:
                    sector_scores['relative_strength'] = 50
            else:
                sector_scores['relative_strength'] = 50
            
            # 计算该板块的加权得分
            sector_score = sum(sector_scores.get(key, 50) * self.weights.get(key, 0.5) 
                              for key in self.weights.keys())
            scores.append(sector_score)
        
        # 返回所有板块的平均得分
        if scores:
            return min(100, max(0, np.mean(scores)))
        return 50

