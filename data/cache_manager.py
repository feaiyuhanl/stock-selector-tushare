"""
缓存管理模块：管理本地SQLite缓存
重构版本：使用组合模式，将功能拆分为多个模块
"""
import pandas as pd
from typing import Dict, List, Optional
from .cache_base import CacheBase
from .fundamental_cache import FundamentalCache
from .kline_cache import KlineCache
from .index_cache import IndexCache


class CacheManager(CacheBase):
    """缓存管理器 - SQLite实现 - 重构版本，使用组合模式"""
    
    def __init__(self, cache_dir: str = "cache"):
        """
        初始化缓存管理器
        Args:
            cache_dir: 缓存目录
        """
        # 初始化基础功能
        super().__init__(cache_dir)
        
        # 组合功能模块
        self.fundamental_cache = FundamentalCache(self)
        self.kline_cache = KlineCache(self)
        self.index_cache = IndexCache(self)
    
    # ========== 基本面和财务数据相关方法 ==========
    
    def get_fundamental(self, stock_code: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        从缓存获取基本面数据（优先从内存缓存读取，避免重复读取数据库）
        Args:
            stock_code: 股票代码
            force_refresh: 是否强制刷新
        Returns:
            基本面数据字典
        """
        return self.fundamental_cache.get_fundamental(stock_code, force_refresh)
    
    def save_fundamental(self, stock_code: str, data: Dict):
        """
        保存基本面数据到缓存
        Args:
            stock_code: 股票代码
            data: 基本面数据
        """
        self.fundamental_cache.save_fundamental(stock_code, data)
    
    def batch_save_fundamental(self, data_dict: Dict[str, Dict]):
        """
        批量保存基本面数据（提高效率，使用SQLite事务）
        Args:
            data_dict: {stock_code: data_dict} 字典
        """
        self.fundamental_cache.batch_save_fundamental(data_dict)
    
    def get_financial(self, stock_code: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        从缓存获取财务数据（优先从内存缓存读取，避免重复读取数据库）
        Args:
            stock_code: 股票代码
            force_refresh: 是否强制刷新
        Returns:
            财务数据字典
        """
        return self.fundamental_cache.get_financial(stock_code, force_refresh)
    
    def save_financial(self, stock_code: str, data: Dict):
        """
        保存财务数据到缓存
        Args:
            stock_code: 股票代码
            data: 财务数据
        """
        self.fundamental_cache.save_financial(stock_code, data)
    
    def batch_save_financial(self, data_dict: Dict[str, Dict]):
        """
        批量保存财务数据（提高效率，使用SQLite事务）
        Args:
            data_dict: {stock_code: data_dict} 字典
        """
        self.fundamental_cache.batch_save_financial(data_dict)
    
    # ========== K线数据相关方法 ==========
    
    def get_kline(self, symbol: str, cache_type: str = 'stock',
                  period: str = 'daily', force_refresh: bool = False) -> Optional[pd.DataFrame]:
        """
        从缓存获取K线数据（智能检查最新交易日数据）
        Args:
            symbol: 股票代码/板块名称/概念名称
            cache_type: 缓存类型 ('stock', 'sector', 'concept')
            period: 周期 ('daily', 'weekly', 'monthly')
            force_refresh: 是否强制刷新
        Returns:
            K线数据DataFrame
        """
        return self.kline_cache.get_kline(symbol, cache_type, period, force_refresh)
    
    def has_latest_trading_day_data(self, symbol: str, cache_type: str = 'stock',
                                    period: str = 'daily') -> bool:
        """
        检查是否有最新交易日的数据（用于智能跳过下载）
        Args:
            symbol: 股票代码/板块名称/概念名称
            cache_type: 缓存类型 ('stock', 'sector', 'concept')
            period: 周期 ('daily', 'weekly', 'monthly')
        Returns:
            是否有最新交易日数据
        """
        return self.kline_cache.has_latest_trading_day_data(symbol, cache_type, period)
    
    def save_kline(self, symbol: str, data: pd.DataFrame,
                   cache_type: str = 'stock', period: str = 'daily',
                   incremental: bool = True):
        """
        保存K线数据到缓存（支持增量更新和自动清理）
        Args:
            symbol: 股票代码/板块名称/概念名称
            data: K线数据DataFrame
            cache_type: 缓存类型 ('stock', 'sector', 'concept')
            period: 周期 ('daily', 'weekly', 'monthly')
            incremental: 是否增量更新（默认True，会合并现有缓存数据）
        """
        self.kline_cache.save_kline(symbol, data, cache_type, period, incremental)
    
    # ========== 指数权重数据相关方法 ==========
    
    def get_index_weight(
        self,
        index_code: str,
        trade_date: str = None,
        start_date: str = None,
        end_date: str = None,
        force_refresh: bool = False
    ) -> Optional[pd.DataFrame]:
        """
        从缓存获取指数权重数据
        Args:
            index_code: 指数代码，如 '000300.SH'
            trade_date: 交易日期，格式：YYYYMMDD，如果指定则只获取该日期的数据
            start_date: 开始日期，格式：YYYYMMDD
            end_date: 结束日期，格式：YYYYMMDD
            force_refresh: 是否强制刷新
        Returns:
            DataFrame包含以下列：index_code, trade_date, con_code, weight
        """
        return self.index_cache.get_index_weight(
            index_code, trade_date, start_date, end_date, force_refresh
        )
    
    def save_index_weight(
        self,
        index_code: str,
        weight_data: pd.DataFrame
    ):
        """
        保存指数权重数据到缓存（带重试机制）
        Args:
            index_code: 指数代码
            weight_data: 权重数据DataFrame，必须包含 trade_date, con_code, weight 列
        """
        self.index_cache.save_index_weight(index_code, weight_data)
    
    def get_index_weight_history(
        self,
        index_code: str,
        con_code: str,
        start_date: str = None,
        end_date: str = None,
        days: int = 60
    ) -> Optional[pd.DataFrame]:
        """
        获取历史权重数据（用于趋势分析）
        Args:
            index_code: 指数代码
            con_code: 成分股代码
            start_date: 开始日期，格式：YYYYMMDD
            end_date: 结束日期，格式：YYYYMMDD
            days: 回看天数（如果未指定start_date和end_date）
        Returns:
            DataFrame包含 trade_date 和 weight 列，按日期升序排列
        """
        return self.index_cache.get_index_weight_history(
            index_code, con_code, start_date, end_date, days
        )
    
    def calculate_index_weight_factors(
        self,
        index_code: str,
        con_code: str,
        lookback_days: int = 60
    ) -> Optional[Dict]:
        """
        计算指数权重因子（权重变化率、趋势斜率、权重绝对值等）
        Args:
            index_code: 指数代码
            con_code: 成分股代码
            lookback_days: 回看天数
        Returns:
            包含因子值的字典，如果数据不足返回None
        """
        return self.index_cache.calculate_index_weight_factors(
            index_code, con_code, lookback_days
        )
    
    # ========== 工具方法（需要访问多个模块） ==========
    
    def check_cache_completeness(self, stock_codes: List[str], 
                                data_types: List[str] = None) -> Dict[str, Dict]:
        """
        检查缓存完整性，判断是否需要预加载
        Args:
            stock_codes: 股票代码列表
            data_types: 要检查的数据类型列表，如 ['fundamental', 'financial']，None表示检查所有
        Returns:
            缓存完整性统计字典，包含每个类型的覆盖率
        """
        return super().check_cache_completeness(
            stock_codes, data_types, self.fundamental_cache
        )
