"""
指数权重策略：跟踪指数中个股的权重上升趋势
重构版本：使用组合模式，将功能拆分为多个模块
"""
import pandas as pd
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import config
from .base_strategy import BaseStrategy
from .index_evaluator import IndexEvaluator
from .index_data_loader import IndexDataLoader
from scorers.index_weight_scorer import IndexWeightScorer


class IndexWeightStrategy(BaseStrategy):
    """指数权重策略类 - 重构版本，使用组合模式"""
    
    def __init__(self, data_fetcher=None, force_refresh: bool = False, 
                 test_sources: bool = True, index_codes: List[str] = None,
                 lookback_days: int = None, score_weights: Dict[str, float] = None):
        """
        初始化指数权重策略
        Args:
            data_fetcher: 数据获取器
            force_refresh: 是否强制刷新缓存
            test_sources: 是否测试数据源可用性（默认True）
            index_codes: 要追踪的指数代码列表，None表示使用配置中的默认指数
            lookback_days: 回看天数，None表示使用配置中的默认值
            score_weights: 评分权重字典，None表示使用配置中的默认权重
        """
        super().__init__(data_fetcher, force_refresh, test_sources)
        
        # 保存force_refresh为实例属性
        self.force_refresh = force_refresh
        
        # 获取配置
        self.index_codes = index_codes or config.INDEX_WEIGHT_CONFIG['tracked_indices']
        self.lookback_days = lookback_days or config.INDEX_WEIGHT_CONFIG['lookback_days']
        self.score_weights = score_weights or config.INDEX_WEIGHT_CONFIG['score_weights']
        self.multi_index_bonus = config.INDEX_WEIGHT_CONFIG['multi_index_bonus']
        self.index_names = config.INDEX_WEIGHT_CONFIG['index_names']
        
        # 初始化评分器
        scorer = IndexWeightScorer(weights=self.score_weights)
        
        # 组合功能模块
        self.evaluator = IndexEvaluator(scorer, self.index_codes, self.multi_index_bonus)
        self.data_loader = IndexDataLoader(
            self.data_fetcher, self.index_codes, self.lookback_days, 
            self.force_refresh, self.index_names
        )
    
    def _calculate_weight_trend_score(
        self,
        index_code: str,
        stock_code: str
    ) -> Optional[Dict]:
        """
        计算单只股票在指定指数中的权重趋势得分
        Args:
            index_code: 指数代码
            stock_code: 股票代码
        Returns:
            包含得分和详细信息的字典，如果数据不足返回None
        """
        return self.evaluator.calculate_weight_trend_score(
            index_code, stock_code, self.data_fetcher, self.lookback_days
        )
    
    def evaluate_stock(self, stock_code: str, stock_name: str = "") -> Optional[Dict]:
        """
        评估单只股票在指数中的权重上升趋势
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
        Returns:
            评估结果字典
        """
        return self.evaluator.evaluate_stock(
            stock_code, stock_name, self.data_fetcher, self.lookback_days
        )
    
    def _ensure_index_weight_data(self):
        """
        确保指数权重数据已加载（如果缺失则自动获取）
        """
        self.data_loader.ensure_index_weight_data()
    
    def _select_stocks_from_indices(
        self,
        index_group: List[str],
        group_name: str,
        stock_codes: List[str] = None,
        top_n: int = 5,
        board_types: List[str] = None,
        max_workers: int = None
    ) -> pd.DataFrame:
        """
        从指定的指数组中选股（内部辅助方法）
        Args:
            index_group: 指数代码列表
            group_name: 组名（用于显示）
            stock_codes: 股票代码列表，如果为None则评估所有股票
            top_n: 返回前N只股票
            board_types: 板块类型列表，None表示使用默认配置
            max_workers: 最大线程数，None表示使用默认配置
        Returns:
            TOP股票DataFrame（包含 category 列标记来源）
        """
        # 临时保存原始指数代码
        original_index_codes = list(self.index_codes) if self.index_codes else []
        
        # 设置为当前组的指数
        self.index_codes = index_group
        self.evaluator.index_codes = index_group
        self.data_loader.index_codes = index_group
        
        if max_workers is None:
            max_workers = config.DEFAULT_MAX_WORKERS
        
        # 获取股票名称映射
        if stock_codes is None:
            stock_codes_to_eval = self.data_fetcher.get_all_stock_codes(board_types)
            if not stock_codes_to_eval:
                self.index_codes = original_index_codes
                self.evaluator.index_codes = original_index_codes
                self.data_loader.index_codes = original_index_codes
                return pd.DataFrame()
        else:
            stock_codes_to_eval = stock_codes
        
        if self.data_fetcher.stock_list is None or self.data_fetcher.stock_list.empty:
            self.data_fetcher._load_stock_list()
        
        stock_list = self.data_fetcher.stock_list
        if stock_list is not None and not stock_list.empty:
            stock_name_map = dict(zip(stock_list['code'].astype(str).str.zfill(6), stock_list['name']))
        else:
            stock_name_map = {code: code for code in stock_codes_to_eval}
        
        # 评估所有股票
        results = []
        
        def evaluate_single_stock(stock_code: str) -> tuple:
            """评估单只股票（用于多线程）"""
            stock_name = stock_name_map.get(stock_code, stock_code)
            result = self.evaluate_stock(stock_code, stock_name)
            if result is not None:
                return (stock_code, result)
            return (stock_code, None)
        
        # 使用线程池并行评估
        print(f"  评估 {len(stock_codes_to_eval)} 只股票...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(evaluate_single_stock, code): code 
                      for code in stock_codes_to_eval}
            
            with tqdm(total=len(stock_codes_to_eval), desc=f"  {group_name}评估") as pbar:
                for future in as_completed(futures):
                    try:
                        code, result = future.result()
                        if result is not None:
                            results.append(result)
                    except Exception as e:
                        pass  # 忽略单个股票的错误
                    finally:
                        pbar.update(1)
        
        # 恢复原始指数代码
        self.index_codes = original_index_codes
        self.evaluator.index_codes = original_index_codes
        self.data_loader.index_codes = original_index_codes
        
        if not results:
            return pd.DataFrame()
        
        # 转换为DataFrame并排序
        df = pd.DataFrame(results)
        df = df.sort_values('score', ascending=False)
        df = df.head(top_n)
        
        # 添加来源标记
        df['category'] = group_name
        
        # 重置索引
        df.reset_index(drop=True, inplace=True)
        
        # 确保列顺序：code, name, category在前
        if 'code' in df.columns and 'name' in df.columns:
            cols = ['code', 'name', 'category'] + [col for col in df.columns if col not in ['code', 'name', 'category']]
            df = df[cols]
        
        return df
    
    def select_top_stocks(
        self,
        stock_codes: List[str] = None,
        top_n: int = 20,
        index_codes: List[str] = None,
        lookback_days: int = None,
        board_types: List[str] = None,
        max_workers: int = None
    ) -> pd.DataFrame:
        """
        选择TOP股票（基于指数权重上升趋势）
        优化版本：分类选股
        - 第一部分：从沪深300中选出权重股TOP10
        - 第二部分：从中证500和中证2000中选出中小盘TOP10
        
        Args:
            stock_codes: 股票代码列表，如果为None则评估所有股票
            top_n: 返回前N只股票（此参数在此策略中将被忽略，使用固定的分类数量）
            index_codes: 要追踪的指数代码列表，None表示使用配置中的默认指数（此参数将被忽略）
            lookback_days: 回看天数，None表示使用配置中的默认值
            board_types: 板块类型列表，None表示使用默认配置
            max_workers: 最大线程数，None表示使用默认配置
        Returns:
            TOP股票DataFrame（包含 category 列标记来源）
        """
        # 更新配置（如果提供了参数）
        if lookback_days is not None:
            self.lookback_days = lookback_days
            self.data_loader.lookback_days = lookback_days
        
        if max_workers is None:
            max_workers = config.DEFAULT_MAX_WORKERS
        
        # 定义两组指数
        hs300_index = ['000300.SH']  # 沪深300
        small_mid_indices = ['000905.SH', '932000.CSI']  # 中证500 + 中证2000
        
        print("\n" + "=" * 60)
        print("【指数权重策略 - 分类选股】")
        print("=" * 60)
        print(f"第一部分: 沪深300权重股 TOP10")
        print(f"第二部分: 中证500+中证2000中小盘 TOP10")
        print(f"回看天数: {self.lookback_days} 天")
        print("=" * 60)
        
        # 步骤1：确保所有指数的权重数据已加载
        print("\n【步骤1】加载指数权重数据...")
        # 临时设置所有指数，确保数据加载
        all_indices = hs300_index + small_mid_indices
        original_index_codes = list(self.index_codes) if self.index_codes else []
        self.index_codes = all_indices
        self.data_loader.index_codes = all_indices
        self._ensure_index_weight_data()
        # 恢复原始指数代码（如果有）
        self.index_codes = original_index_codes
        self.data_loader.index_codes = original_index_codes
        
        # 步骤2：第一部分 - 从沪深300中选TOP10
        print("\n" + "-" * 60)
        print("【第一部分】沪深300权重股选股")
        print("-" * 60)
        hs300_df = self._select_stocks_from_indices(
            index_group=hs300_index,
            group_name='沪深300权重股',
            stock_codes=stock_codes,
            top_n=10,
            board_types=board_types,
            max_workers=max_workers
        )
        
        if not hs300_df.empty:
            print(f"\n✓ 沪深300权重股选股完成，选出 {len(hs300_df)} 只股票")
        else:
            print(f"\n⚠ 沪深300权重股选股未找到符合条件的股票")
        
        # 步骤3：第二部分 - 从中证500+中证2000中选TOP10
        print("\n" + "-" * 60)
        print("【第二部分】中证500+中证2000中小盘选股")
        print("-" * 60)
        small_mid_df = self._select_stocks_from_indices(
            index_group=small_mid_indices,
            group_name='中小盘',
            stock_codes=stock_codes,
            top_n=10,
            board_types=board_types,
            max_workers=max_workers
        )
        
        if not small_mid_df.empty:
            print(f"\n✓ 中小盘选股完成，选出 {len(small_mid_df)} 只股票")
        else:
            print(f"\n⚠ 中小盘选股未找到符合条件的股票")
        
        # 步骤4：合并结果
        print("\n" + "=" * 60)
        print("【合并结果】")
        print("=" * 60)
        
        if hs300_df.empty and small_mid_df.empty:
            print("  未找到符合条件的股票")
            return pd.DataFrame()
        
        # 合并两个DataFrame
        result_dfs = []
        if not hs300_df.empty:
            result_dfs.append(hs300_df)
        if not small_mid_df.empty:
            result_dfs.append(small_mid_df)
        
        final_df = pd.concat(result_dfs, ignore_index=True)
        
        # 重新编号（从1开始）
        final_df.index = final_df.index + 1
        
        print(f"\n✓ 选股完成")
        print(f"  沪深300权重股: {len(hs300_df)} 只")
        print(f"  中小盘: {len(small_mid_df)} 只")
        print(f"  总计: {len(final_df)} 只")
        
        return final_df
