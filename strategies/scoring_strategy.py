"""
打分策略：多维度打分选股策略
重构版本：使用组合模式，将功能拆分为多个模块
"""
import pandas as pd
from typing import List, Dict, Optional
from .base_strategy import BaseStrategy
from .scoring_evaluator import ScoringEvaluator
from .scoring_preloader import ScoringPreloader
from scorers import (
    FundamentalScorer,
    VolumeScorer,
    PriceScorer,
)
import config


class ScoringStrategy(BaseStrategy):
    """打分策略类 - 重构版本，使用组合模式"""
    
    def __init__(self, data_fetcher=None, force_refresh: bool = False, test_sources: bool = True):
        """
        初始化打分策略
        Args:
            data_fetcher: 数据获取器
            force_refresh: 是否强制刷新缓存
            test_sources: 是否测试数据源可用性（默认True）
        """
        super().__init__(data_fetcher, force_refresh, test_sources)
        
        # 初始化评分器
        fundamental_scorer = FundamentalScorer()
        volume_scorer = VolumeScorer()
        price_scorer = PriceScorer()
        weights = config.WEIGHT_CONFIG
        
        # 组合功能模块
        self.evaluator = ScoringEvaluator(fundamental_scorer, volume_scorer, price_scorer, weights)
        self.preloader = ScoringPreloader(self.data_fetcher, self.evaluator)
        
        # 保存权重配置（用于动态调整）
        self.weights = weights
        self._last_adjusted_weights = weights.copy()
    
    def evaluate_stock(self, stock_code: str, stock_name: str = "", 
                      progress_callback=None) -> Optional[Dict]:
        """
        评估单只股票
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            progress_callback: 进度回调函数，接收(status, message)参数
        Returns:
            评估结果字典
        """
        return self.evaluator.evaluate_stock(
            stock_code, stock_name, progress_callback, self.data_fetcher
        )
    
    def preload_all_data(self, stock_codes: List[str], stock_name_map: Dict[str, str],
                        max_workers: int = None) -> Dict[str, Dict]:
        """
        预加载所有股票的数据（数据获取阶段）
        Args:
            stock_codes: 股票代码列表
            stock_name_map: 股票名称映射字典
            max_workers: 最大线程数
        Returns:
            预加载的数据字典，格式为 {stock_code: {kline_data, fundamental_data, financial_data}}
        """
        return self.preloader.preload_all_data(stock_codes, stock_name_map, max_workers)
    
    def calculate_scores_from_preloaded_data(self, preloaded_data: Dict[str, Dict], 
                                            stock_name_map: Dict[str, str]) -> List[Dict]:
        """
        基于预加载的数据计算评分（计算阶段）
        Args:
            preloaded_data: 预加载的数据字典
            stock_name_map: 股票名称映射字典
        Returns:
            评估结果列表
        """
        return self.preloader.calculate_scores_from_preloaded_data(preloaded_data, stock_name_map)
    
    def select_top_stocks(self, stock_codes: List[str] = None, top_n: int = 20, 
                         board_types: List[str] = None, max_workers: int = None) -> pd.DataFrame:
        """
        选择TOP股票（支持多线程）
        Args:
            stock_codes: 股票代码列表，如果为None则评估所有股票
            top_n: 返回前N只股票
            board_types: 板块类型列表，如 ['main', 'gem']，None表示所有板块
            max_workers: 最大线程数（None表示使用配置中的默认值）
        Returns:
            TOP股票DataFrame
        """
        if stock_codes is None:
            # 如果没有指定板块类型，默认使用主板
            if board_types is None:
                board_types = ['main']
            # 获取股票代码（支持板块筛选）
            stock_codes = self.data_fetcher.get_all_stock_codes(board_types)
            # 确保所有代码都是字符串类型
            stock_codes = [str(code) for code in stock_codes]
            print(f"\n【股票筛选】")
            print(f"  获取到 {len(stock_codes)} 只股票（板块: {board_types}）")
            if 'main' in board_types:
                # 统计主板股票分布
                shanghai_main = len([c for c in stock_codes if str(c).startswith('60')])
                shenzhen_main = len([c for c in stock_codes if str(c).startswith('00')])
                print(f"  其中：上证主板 {shanghai_main} 只，深圳主板 {shenzhen_main} 只")
        
        # 准备股票名称映射
        # 优化：确保股票列表已加载（延迟加载）
        if self.data_fetcher.stock_list is None or self.data_fetcher.stock_list.empty:
            self.data_fetcher._load_stock_list()
        stock_info = self.data_fetcher.stock_list
        stock_name_map = {}
        if stock_info is not None and not stock_info.empty:
            for _, row in stock_info.iterrows():
                # 确保代码格式一致（转换为字符串并去除前导零等）
                code = str(row['code']).zfill(6)  # 确保是6位数字
                name = str(row['name']).strip()  # 去除空格
                stock_name_map[code] = name
                # 也支持不带前导零的格式
                stock_name_map[str(int(code))] = name
        
        # 过滤ST股票
        def is_st_stock(stock_code: str) -> bool:
            """判断是否为ST股票"""
            stock_name = stock_name_map.get(stock_code, "")
            if not stock_name:
                return False
            # ST股票名称通常包含"ST"或"*ST"
            return 'ST' in stock_name or '*ST' in stock_name
        
        # 剔除ST股票
        filtered_stock_codes = [code for code in stock_codes if not is_st_stock(code)]
        st_count = len(stock_codes) - len(filtered_stock_codes)
        if st_count > 0:
            print(f"  已剔除 {st_count} 只ST股票")
        stock_codes = filtered_stock_codes
        total = len(stock_codes)
        
        # 预加载所有数据（数据获取阶段）
        # 如果max_workers为None，使用配置中的默认值
        if max_workers is None:
            max_workers = config.DEFAULT_MAX_WORKERS
        preloaded_data = self.preload_all_data(stock_codes, stock_name_map, max_workers)
        
        if not preloaded_data:
            print("\n【错误】")
            print("  没有成功预加载任何数据，无法进行计算")
            empty_df = pd.DataFrame()
            # 存储总股票数（即使为空也记录）
            if hasattr(empty_df, 'attrs'):
                empty_df.attrs['total_stocks_analyzed'] = total
            else:
                empty_df._total_stocks_analyzed = total
            return empty_df
        
        # 基于预加载的数据计算评分（计算阶段）
        results = self.calculate_scores_from_preloaded_data(preloaded_data, stock_name_map)
        
        # 数据可用性统计（用于动态调整权重）
        data_availability = {
            'fundamental': {'available': 0, 'total': 0},
            'financial': {'available': 0, 'total': 0},
        }
        
        def collect_data_availability(results_list: List[Dict]):
            """收集数据可用性统计"""
            for result in results_list:
                # 统计基本面数据可用性
                data_availability['fundamental']['total'] += 1
                pe_ratio = result.get('pe_ratio')
                pb_ratio = result.get('pb_ratio')
                # 改进：区分None（数据缺失）和0（数据为0，如亏损股的PE=0）
                # 如果至少有一个不是None（包括0），视为有数据
                if pe_ratio is not None or pb_ratio is not None:
                    data_availability['fundamental']['available'] += 1
                
                # 统计财务数据可用性
                data_availability['financial']['total'] += 1
                roe = result.get('roe')
                # 改进：区分None（数据缺失）和0（数据为0）
                # 如果roe不是None（包括0），视为有数据
                if roe is not None:
                    data_availability['financial']['available'] += 1
        
        def adjust_weights_by_availability(availability_stats: Dict) -> Dict:
            """
            根据数据可用性动态调整权重
            如果所有股票都缺失某个指标，则不赋予权重
            如果部分股票有、部分没有，等待所有股票获取完成后再决定
            """
            adjusted_weights = self.weights.copy()
            total_stocks = availability_stats['fundamental']['total']
            
            if total_stocks == 0:
                return adjusted_weights
            
            # 检查各维度数据可用性
            fundamental_ratio = availability_stats['fundamental']['available'] / total_stocks if total_stocks > 0 else 0
            financial_ratio = availability_stats['financial']['available'] / total_stocks if total_stocks > 0 else 0
            
            # 如果所有股票都缺失某个指标，权重设为0
            if fundamental_ratio == 0:
                adjusted_weights['fundamental'] = 0
                print(f"  ⚠ 警告: 所有股票都缺失基本面数据，已移除基本面权重")
            
            if financial_ratio == 0:
                adjusted_weights['fundamental'] = 0  # 财务数据影响基本面评分
                print(f"  ⚠ 警告: 所有股票都缺失财务数据，已移除基本面权重")
            
            # 重新归一化权重（确保总和为1）
            total_weight = sum(adjusted_weights.values())
            if total_weight > 0:
                for key in adjusted_weights:
                    adjusted_weights[key] = adjusted_weights[key] / total_weight
            else:
                # 如果所有权重都为0，使用默认权重
                print("  ⚠ 警告: 所有权重都为0，使用默认权重")
                adjusted_weights = self.weights.copy()
            
            return adjusted_weights
        
        # 收集数据可用性统计
        if results:
            collect_data_availability(results)
            
            # 根据数据可用性动态调整权重
            fundamental_ratio = data_availability['fundamental']['available']/data_availability['fundamental']['total']*100 if data_availability['fundamental']['total'] > 0 else 0
            financial_ratio = data_availability['financial']['available']/data_availability['financial']['total']*100 if data_availability['financial']['total'] > 0 else 0
            print(f"\n【数据可用性】")
            print(f"  基本面: {data_availability['fundamental']['available']}/{data_availability['fundamental']['total']} ({fundamental_ratio:.1f}%)")
            print(f"  财务: {data_availability['financial']['available']}/{data_availability['financial']['total']} ({financial_ratio:.1f}%)")
            
            # 动态调整权重并重新计算得分
            adjusted_weights = adjust_weights_by_availability(data_availability)
            # 保存调整后的权重，供主程序访问
            self._last_adjusted_weights = adjusted_weights.copy()
            if adjusted_weights != self.weights:
                # 使用调整后的权重重新计算得分
                print("\n【权重调整】")
                print("  根据数据可用性调整权重并重新计算得分...")
                for result in results:
                    # 重新计算综合得分
                    total_score = (
                        (result.get('fundamental_score') or 0) * adjusted_weights['fundamental'] +
                        (result.get('volume_score') or 0) * adjusted_weights['volume'] +
                        (result.get('price_score') or 0) * adjusted_weights['price']
                    )
                    result['score'] = round(total_score, 2)
                    result['total_score'] = round(total_score, 2)
            else:
                # 即使没有调整，也保存当前权重
                self._last_adjusted_weights = self.weights.copy()
        
        if not results:
            print("\n【结果】")
            print("  未找到符合条件的股票")
            empty_df = pd.DataFrame()
            # 存储总股票数（即使为空也记录）
            if hasattr(empty_df, 'attrs'):
                empty_df.attrs['total_stocks_analyzed'] = total
            else:
                empty_df._total_stocks_analyzed = total
            return empty_df
        
        # 转换为DataFrame并排序
        df = pd.DataFrame(results)
        
        # 确保name列存在且不为空，如果为空则从stock_name_map补充
        if 'name' in df.columns:
            for idx, row in df.iterrows():
                if pd.isna(row['name']) or str(row['name']).strip() == '':
                    code = str(row['code']).zfill(6)
                    df.at[idx, 'name'] = stock_name_map.get(code, stock_name_map.get(str(int(code)), ''))
        
        # 使用score字段排序（策略基类要求）
        sort_column = 'score' if 'score' in df.columns else 'total_score'
        df = df.sort_values(sort_column, ascending=False)
        df = df.head(top_n)
        
        # 重置索引
        df.reset_index(drop=True, inplace=True)
        df.index = df.index + 1  # 从1开始编号
        
        # 确保列顺序：code, name在前
        if 'code' in df.columns and 'name' in df.columns:
            cols = ['code', 'name'] + [col for col in df.columns if col not in ['code', 'name']]
            df = df[cols]
        
        # 存储总股票数到DataFrame的attrs属性中（pandas 1.3+）
        # 如果attrs不可用，使用自定义属性作为备选
        if hasattr(df, 'attrs'):
            df.attrs['total_stocks_analyzed'] = total
        else:
            # 对于旧版本pandas，使用自定义属性
            df._total_stocks_analyzed = total
        
        return df
