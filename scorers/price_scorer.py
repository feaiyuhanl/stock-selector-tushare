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
    
    def score(self, kline_data: pd.DataFrame) -> dict:
        """
        计算价格综合得分和详细指标
        Args:
            kline_data: K线数据（包含价格信息）
        Returns:
            字典包含：score（综合得分）、price_trend、price_position、volatility等指标
        """
        if kline_data is None or kline_data.empty:
            return {'score': 50, 'price_trend': None, 'price_position': None, 'volatility': None}

        scores = {}
        closes = kline_data['close'].values

        if len(closes) < 5:
            return {'score': 50, 'price_trend': None, 'price_position': None, 'volatility': None}

        current_price = closes[-1]

        # 1. 价格趋势评分（上升趋势较好）
        price_trend_ratio = None
        if len(closes) >= 20:
            # 计算短期和长期均线
            short_ma = np.mean(closes[-5:])
            long_ma = np.mean(closes[-20:])

            # 计算趋势强度
            if long_ma > 0:
                price_trend_ratio = short_ma / long_ma
                # 短期均线在长期均线上方，且价格在短期均线上方
                price_above_short = current_price >= short_ma

                if price_trend_ratio >= 1.05 and price_above_short:
                    scores['price_trend'] = 100
                elif price_trend_ratio >= 1.02 and price_above_short:
                    scores['price_trend'] = 85
                elif price_trend_ratio >= 1.0:
                    scores['price_trend'] = 70
                elif price_trend_ratio >= 0.98:
                    scores['price_trend'] = 50
                else:
                    scores['price_trend'] = max(0, 30)
            else:
                scores['price_trend'] = 50
        else:
            # 简单趋势判断
            recent_trend = (closes[-1] - closes[-min(5, len(closes))]) / closes[-min(5, len(closes))]
            price_trend_ratio = recent_trend
            if recent_trend > 0.05:
                scores['price_trend'] = 85
            elif recent_trend > 0:
                scores['price_trend'] = 70
            else:
                scores['price_trend'] = 50

        # 2. 价格位置评分（相对高低位）
        price_position_ratio = None
        if len(closes) >= 20:
            period_high = np.max(closes[-20:])
            period_low = np.min(closes[-20:])

            if period_high > period_low:
                price_position_ratio = (current_price - period_low) / (period_high - period_low)
                # 在30%-70%区间较好，避免追高和抄底
                if 0.3 <= price_position_ratio <= 0.7:
                    scores['price_position'] = 100
                elif 0.2 <= price_position_ratio < 0.3 or 0.7 < price_position_ratio <= 0.8:
                    scores['price_position'] = 80
                elif 0.1 <= price_position_ratio < 0.2 or 0.8 < price_position_ratio <= 0.9:
                    scores['price_position'] = 60
                else:
                    scores['price_position'] = 40
            else:
                scores['price_position'] = 50
        else:
            scores['price_position'] = 50

        # 3. 波动率评分（适度波动较好）
        volatility_value = None
        if len(closes) >= 10:
            # 计算收益率标准差作为波动率
            returns = np.diff(closes) / closes[:-1]
            volatility_value = np.std(returns) * np.sqrt(252)  # 年化波动率

            # 波动率在20%-40%之间较好
            if 0.20 <= volatility_value <= 0.40:
                scores['volatility'] = 100
            elif 0.15 <= volatility_value < 0.20 or 0.40 < volatility_value <= 0.50:
                scores['volatility'] = 80
            elif 0.10 <= volatility_value < 0.15 or 0.50 < volatility_value <= 0.60:
                scores['volatility'] = 60
            else:
                scores['volatility'] = max(0, 40)
        else:
            scores['volatility'] = 50

        # 计算加权总分
        total_score = sum(scores.get(key, 50) * self.weights.get(key, 0)
                         for key in self.weights.keys())
        total_score = min(100, max(0, total_score))

        return {
            'score': total_score,
            'price_trend': price_trend_ratio,
            'price_position': price_position_ratio,
            'volatility': volatility_value,
            'price_trend_score': scores.get('price_trend', 50),
            'price_position_score': scores.get('price_position', 50),
            'volatility_score': scores.get('volatility', 50)
        }

