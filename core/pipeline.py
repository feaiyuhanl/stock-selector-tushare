"""
选股流程管道：统一管理完整的选股流程
"""
import pandas as pd
from typing import Tuple, Optional, TYPE_CHECKING
import config

if TYPE_CHECKING:
    from stock_selector import StockSelector
    from core.executor import StrategyExecutor


class SelectionPipeline:
    """选股流程管道，统一管理执行流程"""
    
    def __init__(self, executor: 'StrategyExecutor'):
        """
        初始化选股流程管道
        Args:
            executor: 策略执行器实例
        """
        self.executor = executor
        self._current_selector: Optional['StockSelector'] = None
        self._current_selector_fundamental: Optional['StockSelector'] = None
        self._current_selector_index_weight: Optional['StockSelector'] = None
    
    def run(self, args, 
            run_feishu_sync_func,
            send_notification_func):
        """
        执行完整的选股流程
        Args:
            args: 命令行参数对象
            run_feishu_sync_func: 飞书同步函数
            send_notification_func: 发送通知函数
        """
        if args.factor_set == 'combined':
            self._run_combined(args, run_feishu_sync_func, send_notification_func)
        else:
            self._run_single(args, run_feishu_sync_func, send_notification_func)
    
    def _run_single(self, args, run_feishu_sync_func, send_notification_func):
        """单策略流程"""
        # 执行选股
        results, selector = self.executor.execute(args)
        self._current_selector = selector
        
        # 后处理：复盘、飞书、通知
        self._post_process(args, results, selector, run_feishu_sync_func, send_notification_func)
    
    def _run_combined(self, args, run_feishu_sync_func, send_notification_func):
        """Combined策略流程"""
        import argparse
        
        # 创建两个策略的参数副本
        args_fundamental = argparse.Namespace(**vars(args))
        args_fundamental.factor_set = 'fundamental'
        args_index_weight = argparse.Namespace(**vars(args))
        args_index_weight.factor_set = 'index_weight'
        
        # 执行合并策略
        results_f, selector_f, results_i, selector_i = self.executor.execute_combined(
            args_fundamental, args_index_weight
        )
        self._current_selector_fundamental = selector_f
        self._current_selector_index_weight = selector_i
        
        # 后处理：复盘、飞书、通知
        self._post_process_combined(
            args, results_f, results_i, selector_f, selector_i,
            run_feishu_sync_func, send_notification_func
        )
    
    def _post_process(self, args, results: pd.DataFrame, selector: 'StockSelector',
                     run_feishu_sync_func, send_notification_func):
        """后处理：保存、复盘、飞书、通知（单策略）"""
        # 自动复盘（由 config.AUTO_REVIEW_CONFIG.enabled 控制）
        if config.AUTO_REVIEW_CONFIG.get('enabled', True):
            try:
                from autoreview import AutoReview
                auto_review = AutoReview(
                    selector.strategy.data_fetcher,
                    selector.strategy.data_fetcher.cache_manager
                )
                auto_review.auto_review_last_n_days()
            except Exception as e:
                print(f"[警告] 自动复盘失败: {e}")
        
        # 飞书复盘结果同步（由 config.FEISHU_SHEETS_CONFIG.enabled 控制）
        try:
            run_feishu_sync_func(
                selector.strategy.data_fetcher.cache_manager,
                [selector.strategy.get_strategy_name()],
            )
        except Exception as e:
            print(f"[警告] 飞书同步失败: {e}")
        
        # 发送通知
        if args.notify:
            send_notification_func(args, results, selector)
    
    def _post_process_combined(self, args, 
                              results_fundamental: pd.DataFrame, results_index_weight: pd.DataFrame,
                              selector_fundamental: 'StockSelector', selector_index_weight: 'StockSelector',
                              run_feishu_sync_func, send_notification_func):
        """后处理：保存、复盘、飞书、通知（合并策略）"""
        # 自动复盘（由 config.AUTO_REVIEW_CONFIG.enabled 控制）
        if config.AUTO_REVIEW_CONFIG.get('enabled', True):
            try:
                from autoreview import AutoReview
                auto_review = AutoReview(
                    selector_fundamental.strategy.data_fetcher,
                    selector_fundamental.strategy.data_fetcher.cache_manager
                )
                auto_review.auto_review_last_n_days()
            except Exception as e:
                print(f"[警告] 自动复盘失败: {e}")
        
        # 飞书复盘结果同步（由 config.FEISHU_SHEETS_CONFIG.enabled 控制）
        try:
            run_feishu_sync_func(
                selector_fundamental.strategy.data_fetcher.cache_manager,
                ['ScoringStrategy', 'IndexWeightStrategy'],
            )
        except Exception as e:
            print(f"[警告] 飞书同步失败: {e}")
        
        # 发送通知（合并两个策略的结果）
        if args.notify:
            send_notification_func(args, results_fundamental, selector_fundamental,
                                  results_combined=results_index_weight,
                                  selector_combined=selector_index_weight)
    
    def get_selector(self) -> Optional['StockSelector']:
        """获取当前的selector（用于错误处理）"""
        return (self._current_selector or 
                self._current_selector_fundamental or
                self._current_selector_index_weight)
    
    def handle_interrupt(self, handle_interrupt_func):
        """处理中断"""
        selector = self.get_selector()
        handle_interrupt_func(selector)
    
    def handle_error(self, error: Exception, handle_execution_error_func):
        """处理执行错误"""
        selector = self.get_selector()
        handle_execution_error_func(selector, error)
