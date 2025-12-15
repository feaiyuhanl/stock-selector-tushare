"""
成交价格评分模块
"""
import numpy as np
import pandas as pd
from typing import Dict, Optional
import config


class PriceScorer:
    """价格评分器"""
    
    def __init__(self):
        self.weights = config.PRICE_WEIGHTS
    
    def score(self, kline_data: pd.DataFrame) -> float:
        """
        计算价格综合得分
        Args:
            kline_data: K线数据（包含价格信息）
        Returns:
            综合得分 0-100
        """
        if kline_data is None or kline_data.empty:
            return 50
        
        scores = {}
        closes = kline_data['close'].values
        
        if len(closes) < 5:
            return 50
        
        current_price = closes[-1]
        
        # 1. 价格趋势评分（上升趋势较好）
        if len(closes) >= 20:
            # 计算短期和长期均线
            short_ma = np.mean(closes[-5:])
            long_ma = np.mean(closes[-20:])
            
            # 计算趋势强度
            if long_ma > 0:
                ma_ratio = short_ma / long_ma
                # 短期均线在长期均线上方，且价格在短期均线上方
                price_above_short = current_price >= short_ma
                
                if ma_ratio >= 1.05 and price_above_short:
                    scores['price_trend'] = 100
                elif ma_ratio >= 1.02 and price_above_short:
                    scores['price_trend'] = 85
                elif ma_ratio >= 1.0:
                    scores['price_trend'] = 70
                elif ma_ratio >= 0.98:
                    scores['price_trend'] = 50
                else:
                    scores['price_trend'] = max(0, 30)
            else:
                scores['price_trend'] = 50
        else:
            # 简单趋势判断
            recent_trend = (closes[-1] - closes[-min(5, len(closes))]) / closes[-min(5, len(closes))]
            if recent_trend > 0.05:
                scores['price_trend'] = 85
            elif recent_trend > 0:
                scores['price_trend'] = 70
            else:
                scores['price_trend'] = 50
        
        # 2. 价格位置评分（相对高低位）
        if len(closes) >= 20:
            period_high = np.max(closes[-20:])
            period_low = np.min(closes[-20:])
            
            if period_high > period_low:
                position_ratio = (current_price - period_low) / (period_high - period_low)
                # 在30%-70%区间较好，避免追高和抄底
                if 0.3 <= position_ratio <= 0.7:
                    scores['price_position'] = 100
                elif 0.2 <= position_ratio < 0.3 or 0.7 < position_ratio <= 0.8:
                    scores['price_position'] = 80
                elif 0.1 <= position_ratio < 0.2 or 0.8 < position_ratio <= 0.9:
                    scores['price_position'] = 60
                else:
                    scores['price_position'] = 40
            else:
                scores['price_position'] = 50
        else:
            scores['price_position'] = 50
        
        # 3. 波动率评分（适度波动较好）
        if len(closes) >= 10:
            # 计算收益率标准差作为波动率
            returns = np.diff(closes) / closes[:-1]
            volatility = np.std(returns) * np.sqrt(252)  # 年化波动率
            
            # 波动率在20%-40%之间较好
            if 0.20 <= volatility <= 0.40:
                scores['volatility'] = 100
            elif 0.15 <= volatility < 0.20 or 0.40 < volatility <= 0.50:
                scores['volatility'] = 80
            elif 0.10 <= volatility < 0.15 or 0.50 < volatility <= 0.60:
                scores['volatility'] = 60
            else:
                scores['volatility'] = max(0, 40)
        else:
            scores['volatility'] = 50
        
        # 计算加权总分
        total_score = sum(scores.get(key, 50) * self.weights.get(key, 0) 
                         for key in self.weights.keys())
        
        return min(100, max(0, total_score))

