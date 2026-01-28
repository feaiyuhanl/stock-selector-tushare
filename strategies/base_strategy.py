"""
基础策略类：所有选股策略的基类
"""
from abc import ABC, abstractmethod
import pandas as pd
from typing import List, Dict, Optional
from data.fetcher import DataFetcher


class BaseStrategy(ABC):
    """选股策略基类"""
    
    def __init__(self, data_fetcher: DataFetcher = None, force_refresh: bool = False, test_sources: bool = True):
        """
        初始化策略
        Args:
            data_fetcher: 数据获取器，如果为None则创建新的
            force_refresh: 是否强制刷新缓存
            test_sources: 是否测试数据源可用性（默认True）
        """
        if data_fetcher is None:
            self.data_fetcher = DataFetcher(force_refresh=force_refresh, test_sources=test_sources)
        else:
            self.data_fetcher = data_fetcher
    
    @property
    def strategy_type(self) -> str:
        """
        获取策略类型
        Returns:
            策略类型：'fundamental' 或 'index_weight'
        """
        strategy_name = self.get_strategy_name()
        if strategy_name == 'ScoringStrategy':
            return 'fundamental'
        elif strategy_name == 'IndexWeightStrategy':
            return 'index_weight'
        else:
            return 'unknown'
    
    @abstractmethod
    def evaluate_stock(self, stock_code: str, stock_name: str = "") -> Optional[Dict]:
        """
        评估单只股票
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
        Returns:
            评估结果字典，必须包含 'code', 'name', 'score' 字段
        """
        pass
    
    @abstractmethod
    def select_top_stocks(self, stock_codes: List[str] = None, top_n: int = 20,
                         board_types: List[str] = None, max_workers: int = None,
                         **kwargs) -> pd.DataFrame:
        """
        选择TOP股票 - 统一接口，支持额外参数
        Args:
            stock_codes: 股票代码列表，如果为None则评估所有股票
            top_n: 返回前N只股票
            board_types: 板块类型列表，None表示使用默认配置
            max_workers: 最大线程数，None表示使用默认配置
            **kwargs: 额外参数（不同策略可能有不同的额外参数）
        Returns:
            TOP股票DataFrame
        """
        pass
    
    def get_strategy_name(self) -> str:
        """
        获取策略名称
        Returns:
            策略名称
        """
        return self.__class__.__name__

