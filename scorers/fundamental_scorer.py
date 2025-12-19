"""
基本面评分模块
"""
import numpy as np
from typing import Dict, Optional
import config


class FundamentalScorer:
    """基本面评分器"""
    
    def __init__(self):
        self.weights = config.FUNDAMENTAL_WEIGHTS
    
    def score(self, fundamental_data: Dict, financial_data: Dict) -> dict:
        """
        计算基本面综合得分和详细指标
        Args:
            fundamental_data: 基本面数据（PE、PB等）
            financial_data: 财务数据（ROE、增长率等）
        Returns:
            字典包含：score（综合得分）以及各项指标得分
        """
        scores = {}
        
        # 1. 市盈率评分（越低越好，但也要考虑行业）
        pe_ratio = fundamental_data.get('pe_ratio')
        # 改进：正确处理 None 值（数据缺失）和 0 值（可能是正常值，如亏损股）
        if pe_ratio is not None and pe_ratio > 0:
            # PE在0-50之间给分，50以上递减
            if pe_ratio <= 20:
                scores['pe_ratio'] = 100
            elif pe_ratio <= 30:
                scores['pe_ratio'] = 80
            elif pe_ratio <= 50:
                scores['pe_ratio'] = 60
            else:
                scores['pe_ratio'] = max(0, 60 - (pe_ratio - 50) * 2)
        elif pe_ratio == 0:
            # PE为0可能是亏损股，给中等偏下分
            scores['pe_ratio'] = 40
        else:
            scores['pe_ratio'] = 50  # 无数据（None）给中等分
        
        # 2. 市净率评分（越低越好）
        pb_ratio = fundamental_data.get('pb_ratio')
        # 改进：正确处理 None 值（数据缺失）和 0 值
        if pb_ratio is not None and pb_ratio > 0:
            if pb_ratio <= 1:
                scores['pb_ratio'] = 100
            elif pb_ratio <= 2:
                scores['pb_ratio'] = 80
            elif pb_ratio <= 3:
                scores['pb_ratio'] = 60
            elif pb_ratio <= 5:
                scores['pb_ratio'] = 40
            else:
                scores['pb_ratio'] = max(0, 40 - (pb_ratio - 5) * 5)
        elif pb_ratio == 0:
            # PB为0可能是特殊情况，给中等偏下分
            scores['pb_ratio'] = 40
        else:
            scores['pb_ratio'] = 50  # 无数据（None）给中等分
        
        # 3. ROE评分（越高越好）
        roe = financial_data.get('roe', 0)
        if roe:
            if roe >= 20:
                scores['roe'] = 100
            elif roe >= 15:
                scores['roe'] = 85
            elif roe >= 10:
                scores['roe'] = 70
            elif roe >= 5:
                scores['roe'] = 50
            else:
                scores['roe'] = max(0, 50 + roe * 2)
        else:
            scores['roe'] = 50
        
        # 4. 营收增长率评分（越高越好）
        revenue_growth = financial_data.get('revenue_growth', 0)
        if revenue_growth:
            if revenue_growth >= 50:
                scores['revenue_growth'] = 100
            elif revenue_growth >= 30:
                scores['revenue_growth'] = 85
            elif revenue_growth >= 15:
                scores['revenue_growth'] = 70
            elif revenue_growth >= 0:
                scores['revenue_growth'] = 50
            else:
                scores['revenue_growth'] = max(0, 50 + revenue_growth)
        else:
            scores['revenue_growth'] = 50
        
        # 5. 利润增长率评分（越高越好）
        profit_growth = financial_data.get('profit_growth', 0)
        if profit_growth:
            if profit_growth >= 50:
                scores['profit_growth'] = 100
            elif profit_growth >= 30:
                scores['profit_growth'] = 85
            elif profit_growth >= 15:
                scores['profit_growth'] = 70
            elif profit_growth >= 0:
                scores['profit_growth'] = 50
            else:
                scores['profit_growth'] = max(0, 50 + profit_growth)
        else:
            scores['profit_growth'] = 50
        
        # 计算加权总分
        total_score = sum(scores.get(key, 50) * self.weights.get(key, 0)
                         for key in self.weights.keys())
        total_score = min(100, max(0, total_score))

        return {
            'score': total_score,
            'pe_ratio': pe_ratio,
            'pb_ratio': pb_ratio,
            'roe': roe,
            'revenue_growth': revenue_growth,
            'profit_growth': profit_growth,
            'pe_ratio_score': scores.get('pe_ratio', 50),
            'pb_ratio_score': scores.get('pb_ratio', 50),
            'roe_score': scores.get('roe', 50),
            'revenue_growth_score': scores.get('revenue_growth', 50),
            'profit_growth_score': scores.get('profit_growth', 50)
        }

