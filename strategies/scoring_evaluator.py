"""
打分策略评估器：单只股票评估逻辑
"""
import pandas as pd
from datetime import datetime
from typing import Dict, Optional
from scorers import (
    FundamentalScorer,
    VolumeScorer,
    PriceScorer,
)


class ScoringEvaluator:
    """打分策略评估器"""
    
    def __init__(self, fundamental_scorer, volume_scorer, price_scorer, weights):
        """
        初始化评估器
        Args:
            fundamental_scorer: 基本面评分器
            volume_scorer: 成交量评分器
            price_scorer: 价格评分器
            weights: 权重配置
        """
        self.fundamental_scorer = fundamental_scorer
        self.volume_scorer = volume_scorer
        self.price_scorer = price_scorer
        self.weights = weights
    
    def evaluate_stock(self, stock_code: str, stock_name: str = "", 
                      progress_callback=None, data_fetcher=None) -> Optional[Dict]:
        """
        评估单只股票
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            progress_callback: 进度回调函数，接收(status, message)参数
            data_fetcher: 数据获取器
        Returns:
            评估结果字典
        """
        try:
            if progress_callback:
                progress_callback('loading', f"加载 {stock_code} {stock_name} 的数据...")
            
            # 1. 获取K线数据
            if progress_callback:
                progress_callback('loading', f"{stock_code} {stock_name}: 获取K线数据...")
            kline_data = data_fetcher.get_stock_kline(stock_code)
            if kline_data is None or kline_data.empty:
                if progress_callback:
                    progress_callback('failed', f"{stock_code} {stock_name}: K线数据获取失败")
                return None
            
            # 2. 获取基本面数据（带缓存）
            if progress_callback:
                progress_callback('loading', f"{stock_code} {stock_name}: 获取基本面数据...")
            fundamental_data = data_fetcher.get_stock_fundamental(stock_code)
            if fundamental_data is None:
                fundamental_data = {}
            
            # 3. 获取财务数据（带缓存）
            if progress_callback:
                progress_callback('loading', f"{stock_code} {stock_name}: 获取财务数据...")
            financial_data = data_fetcher.get_stock_financial(stock_code)
            if financial_data is None:
                financial_data = {}
            
            # 4. 计算各维度得分
            if progress_callback:
                progress_callback('loading', f"{stock_code} {stock_name}: 计算评分...")
            fundamental_result = self.fundamental_scorer.score(fundamental_data, financial_data)
            volume_result = self.volume_scorer.score(kline_data)
            price_result = self.price_scorer.score(kline_data)

            # 提取综合得分
            fundamental_score = fundamental_result['score']
            volume_score = volume_result['score']
            price_score = price_result['score']
            
            # 5. 计算综合得分
            total_score = (
                fundamental_score * self.weights['fundamental'] +
                volume_score * self.weights['volume'] +
                price_score * self.weights['price']
            )
            
            # 6. 获取当前价格信息
            current_price = kline_data['close'].iloc[-1] if not kline_data.empty else 0
            current_volume = kline_data['volume'].iloc[-1] if not kline_data.empty else 0
            current_pct_change = kline_data['pct_change'].iloc[-1] if not kline_data.empty and 'pct_change' in kline_data.columns else 0

            # 获取数据时间（使用最新的K线数据日期）
            data_fetch_time = kline_data['date'].iloc[-1] if not kline_data.empty and 'date' in kline_data.columns else datetime.now()

            result = {
                'code': stock_code,
                'name': stock_name,
                'score': round(total_score, 2),  # 策略基类要求的字段
                'total_score': round(total_score, 2),  # 保持兼容性
                'fundamental_score': round(fundamental_score, 2),
                'volume_score': round(volume_score, 2),
                'price_score': round(price_score, 2),
                'current_price': round(current_price, 2),
                'current_volume': current_volume,
                'pct_change': round(current_pct_change, 2),
                'data_fetch_time': data_fetch_time,
                # 基本面详细指标
                'pe_ratio': fundamental_result.get('pe_ratio'),
                'pb_ratio': fundamental_result.get('pb_ratio'),
                'roe': fundamental_result.get('roe'),
                'revenue_growth': fundamental_result.get('revenue_growth'),
                'profit_growth': fundamental_result.get('profit_growth'),
                # 成交量详细指标
                'volume_ratio': volume_result.get('volume_ratio'),
                'turnover_rate': volume_result.get('turnover_rate'),
                'volume_trend': volume_result.get('volume_trend'),
                # 价格详细指标
                'price_trend': price_result.get('price_trend'),
                'price_position': price_result.get('price_position'),
                'volatility': price_result.get('volatility'),
                # 子维度得分（用于详细展示）
                'pe_ratio_score': fundamental_result.get('pe_ratio_score', 50),
                'pb_ratio_score': fundamental_result.get('pb_ratio_score', 50),
                'roe_score': fundamental_result.get('roe_score', 50),
                'revenue_growth_score': fundamental_result.get('revenue_growth_score', 50),
                'profit_growth_score': fundamental_result.get('profit_growth_score', 50),
                'volume_ratio_score': volume_result.get('volume_ratio_score', 50),
                'turnover_rate_score': volume_result.get('turnover_rate_score', 50),
                'volume_trend_score': volume_result.get('volume_trend_score', 50),
                'price_trend_score': price_result.get('price_trend_score', 50),
                'price_position_score': price_result.get('price_position_score', 50),
                'volatility_score': price_result.get('volatility_score', 50),
            }
            
            if progress_callback:
                progress_callback('success', f"{stock_code} {stock_name}: 评估完成，得分 {result['score']:.2f}")
            
            return result
            
        except Exception as e:
            error_msg = f"评估 {stock_code} {stock_name} 时出错: {e}"
            if progress_callback:
                progress_callback('failed', error_msg)
            else:
                print(error_msg)
            return None
    
    def calculate_score_from_data(self, kline_data: pd.DataFrame, 
                                  fundamental_data: Dict, financial_data: Dict,
                                  stock_code: str, stock_name: str = "") -> Dict:
        """
        基于已有数据计算评分（用于预加载后的批量计算）
        Args:
            kline_data: K线数据
            fundamental_data: 基本面数据
            financial_data: 财务数据
            stock_code: 股票代码
            stock_name: 股票名称
        Returns:
            评估结果字典
        """
        # 计算各维度得分
        fundamental_result = self.fundamental_scorer.score(fundamental_data, financial_data)
        volume_result = self.volume_scorer.score(kline_data)
        price_result = self.price_scorer.score(kline_data)

        # 提取综合得分
        fundamental_score = fundamental_result['score']
        volume_score = volume_result['score']
        price_score = price_result['score']

        # 计算综合得分
        total_score = (
            fundamental_score * self.weights['fundamental'] +
            volume_score * self.weights['volume'] +
            price_score * self.weights['price']
        )
        
        # 获取当前价格信息
        current_price = kline_data['close'].iloc[-1] if not kline_data.empty else 0
        current_volume = kline_data['volume'].iloc[-1] if not kline_data.empty else 0

        result = {
            'code': stock_code,
            'name': stock_name,
            'score': round(total_score, 2),
            'total_score': round(total_score, 2),
            'fundamental_score': round(fundamental_score, 2),
            'volume_score': round(volume_score, 2),
            'price_score': round(price_score, 2),
            'current_price': round(current_price, 2),
            'current_volume': current_volume,
            # 基本面详细指标
            'pe_ratio': fundamental_result.get('pe_ratio'),
            'pb_ratio': fundamental_result.get('pb_ratio'),
            'roe': fundamental_result.get('roe'),
            'revenue_growth': fundamental_result.get('revenue_growth'),
            'profit_growth': fundamental_result.get('profit_growth'),
            # 成交量详细指标
            'volume_ratio': volume_result.get('volume_ratio'),
            'turnover_rate': volume_result.get('turnover_rate'),
            'volume_trend': volume_result.get('volume_trend'),
            # 价格详细指标
            'price_trend': price_result.get('price_trend'),
            'price_position': price_result.get('price_position'),
            'volatility': price_result.get('volatility'),
            # 子维度得分（用于详细展示）
            'pe_ratio_score': fundamental_result.get('pe_ratio_score', 50),
            'pb_ratio_score': fundamental_result.get('pb_ratio_score', 50),
            'roe_score': fundamental_result.get('roe_score', 50),
            'revenue_growth_score': fundamental_result.get('revenue_growth_score', 50),
            'profit_growth_score': fundamental_result.get('profit_growth_score', 50),
            'volume_ratio_score': volume_result.get('volume_ratio_score', 50),
            'turnover_rate_score': volume_result.get('turnover_rate_score', 50),
            'volume_trend_score': volume_result.get('volume_trend_score', 50),
            'price_trend_score': price_result.get('price_trend_score', 50),
            'price_position_score': price_result.get('price_position_score', 50),
            'volatility_score': price_result.get('volatility_score', 50),
        }
        
        return result

