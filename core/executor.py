"""
策略执行器：封装策略创建、执行、保存的完整流程
"""
import pandas as pd
from typing import Tuple


class StrategyExecutor:
    """策略执行器，封装策略创建、执行、保存的完整流程"""
    
    def __init__(self, 
                 create_strategy_func,
                 prepare_params_func,
                 print_startup_info_func,
                 execute_selection_func,
                 save_recommendations_func):
        """
        初始化策略执行器
        Args:
            create_strategy_func: 策略创建函数
            prepare_params_func: 参数准备函数
            print_startup_info_func: 打印启动信息函数
            execute_selection_func: 执行选股函数
            save_recommendations_func: 保存推荐结果函数
        """
        self.create_strategy = create_strategy_func
        self.prepare_params = prepare_params_func
        self.print_startup_info = print_startup_info_func
        self.execute_selection = execute_selection_func
        self.save_recommendations = save_recommendations_func
    
    def execute(self, args) -> Tuple[pd.DataFrame, object]:
        """
        执行单策略选股流程
        Args:
            args: 命令行参数对象
        Returns:
            tuple: (results, selector)
        """
        from utils import print_results
        from stock_selector import StockSelector
        
        # 创建策略
        strategy = self.create_strategy(args)
        selector = StockSelector(strategy=strategy)
        
        # 准备选股参数
        select_params = self.prepare_params(args, strategy)
        
        # 打印状态信息
        self.print_startup_info(args, strategy)
        
        # 执行选股
        results = self.execute_selection(selector, strategy, select_params)
        
        # 输出结果
        print_results(results, selector)
        
        # 保存推荐结果
        self.save_recommendations(selector, strategy, results)
        
        return results, selector
    
    def execute_combined(self, args_fundamental, args_index_weight) -> Tuple[pd.DataFrame, object, pd.DataFrame, object]:
        """
        执行合并策略选股流程（同时运行两个策略）
        Args:
            args_fundamental: 基本面策略的命令行参数对象
            args_index_weight: 指数权重策略的命令行参数对象
        Returns:
            tuple: (results_fundamental, selector_fundamental, results_index_weight, selector_index_weight)
        """
        from utils import print_results
        
        # 运行基本面策略
        print("\n" + "-" * 60)
        print("【策略1】多因子打分策略（基本面+成交量+价格）")
        print("-" * 60)
        results_fundamental, selector_fundamental = self.execute(args_fundamental)
        
        # 运行指数权重策略
        print("\n" + "-" * 60)
        print("【策略2】指数权重选股策略")
        print("-" * 60)
        results_index_weight, selector_index_weight = self.execute(args_index_weight)
        
        # 输出结果
        print("\n" + "=" * 60)
        print("【策略1结果】多因子打分策略")
        print("=" * 60)
        print_results(results_fundamental, selector_fundamental)
        
        print("\n" + "=" * 60)
        print("【策略2结果】指数权重选股策略")
        print("=" * 60)
        print_results(results_index_weight, selector_index_weight)
        
        return results_fundamental, selector_fundamental, results_index_weight, selector_index_weight
