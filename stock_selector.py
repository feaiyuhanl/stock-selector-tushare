"""
A股选股程序主程序 - 支持多策略和缓存管理
"""
# 修复Windows中文编码问题
import fix_encoding

import pandas as pd
from datetime import datetime
from typing import List, Optional
from strategies import ScoringStrategy
from strategies.base_strategy import BaseStrategy
import config
import sys

# 导入工具函数
from utils.token_checker import check_tushare_token

# 导入输出格式化函数
from utils import (
    print_cache_info,
    print_status_info,
    print_results,
)

# 导入通知相关函数
from notifications.helpers import (
    check_notification_throttle,
    prepare_stock_data_for_notification,
    build_notification_body,
)


class StockSelector:
    """股票选择器主类（支持多策略）"""
    
    def __init__(self, strategy: BaseStrategy = None, force_refresh: bool = False):
        """
        初始化股票选择器
        Args:
            strategy: 选股策略，如果为None则使用默认的打分策略
            force_refresh: 是否强制刷新缓存
        """
        if strategy is None:
            self.strategy = ScoringStrategy(force_refresh=force_refresh)
        else:
            self.strategy = strategy
    
    def evaluate_stock(self, stock_code: str, stock_name: str = "") -> Optional[dict]:
        """
        评估单只股票
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
        Returns:
            评估结果字典
        """
        return self.strategy.evaluate_stock(stock_code, stock_name)
    
    def select_top_stocks(self, stock_codes: List[str] = None, top_n: int = None,
                         board_types: List[str] = None, max_workers: int = None) -> pd.DataFrame:
        """
        选择TOP股票
        Args:
            stock_codes: 股票代码列表，如果为None则评估所有股票
            top_n: 返回前N只股票
            board_types: 板块类型列表，如 ['main', 'gem']，None表示使用默认配置
            max_workers: 最大线程数，None表示使用默认配置
        Returns:
            TOP股票DataFrame
        """
        if top_n is None:
            top_n = config.TOP_N
        
        if board_types is None:
            board_types = config.DEFAULT_BOARD_TYPES
        
        if max_workers is None:
            max_workers = config.DEFAULT_MAX_WORKERS
        
        return self.strategy.select_top_stocks(stock_codes, top_n, board_types, max_workers)
    
    def clear_cache(self, cache_type: str = None):
        """
        清除缓存
        Args:
            cache_type: 缓存类型，None表示清除所有
        """
        self.strategy.data_fetcher.cache_manager.clear_cache(cache_type)


def _send_combined_notification(args, results_fundamental: pd.DataFrame, results_index_weight: pd.DataFrame,
                                selector_fundamental: StockSelector, selector_index_weight: StockSelector):
    """
    发送合并策略通知（同时包含两个策略的结果）
    Args:
        args: 命令行参数对象
        results_fundamental: 多因子打分策略结果DataFrame
        results_index_weight: 指数权重策略结果DataFrame
        selector_fundamental: 多因子策略的StockSelector实例
        selector_index_weight: 指数权重策略的StockSelector实例
    """
    try:
        from notifications import get_notifier
    except ImportError:
        print(f"\n[邮件通知] 通知模块未安装，无法发送通知")
        return
    
    try:
        # 目前只支持邮件通知
        notifier = get_notifier('email')
        if not notifier or not notifier.is_available():
            print(f"\n[邮件通知] 服务不可用，请检查配置")
            return
        
        # 收件人优先从命令行参数获取，如果没有指定则从配置文件读取
        if args.notify_to:
            recipients = args.notify_to
        else:
            recipients = config.EMAIL_CONFIG['default_recipients']
        
        # 防骚扰检查（使用fundamental策略的selector）
        filtered_recipients, throttle_manager = check_notification_throttle(args, selector_fundamental, recipients)
        if filtered_recipients is None:
            return  # 防骚扰检查未通过
        
        recipients = filtered_recipients
        if not args.notify_throttle:
            print(f"[邮件通知] 使用收件人: {recipients}")
        
        # 构建通知内容
        subject = f"综合选股策略报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # 准备股票数据（合并两个策略的结果）
        stock_data_fundamental, total_stocks_fundamental = prepare_stock_data_for_notification(results_fundamental)
        stock_data_index_weight, total_stocks_index_weight = prepare_stock_data_for_notification(results_index_weight)
        
        # 计算总股票数（取两个策略中较大的值）
        total_stocks_count = max(total_stocks_fundamental, total_stocks_index_weight)
        
        # 调试信息
        if total_stocks_count > 0:
            print(f"[邮件通知] 多因子策略分析股票数: {total_stocks_fundamental} 只，返回TOP股票: {len(results_fundamental)} 只")
            print(f"[邮件通知] 指数权重策略分析股票数: {total_stocks_index_weight} 只，返回TOP股票: {len(results_index_weight)} 只")
        
        # 发送通知（使用合并策略的模板）
        success = notifier.send_combined_notification(
            subject=subject,
            recipients=recipients,
            stock_data_fundamental=stock_data_fundamental,
            stock_data_index_weight=stock_data_index_weight,
            total_stocks=total_stocks_count
        )
        
        if success:
            print(f"\n[邮件通知] 已发送合并策略报告到: {', '.join(recipients)}")
            
            # 如果启用了防骚扰模式，标记已发送的邮箱地址
            if args.notify_throttle and throttle_manager:
                for email in recipients:
                    throttle_manager.mark_as_sent(email)
        else:
            print(f"\n[邮件通知] 发送失败，请检查邮件配置")
    
    except Exception as e:
        print(f"\n[邮件通知] 发送出错: {e}")
        print(f"[提示] 请检查邮件配置或网络连接")


def _send_notification(args, results: pd.DataFrame, selector: StockSelector):
    """
    发送通知
    Args:
        args: 命令行参数对象
        results: 选股结果DataFrame
        selector: StockSelector实例
    """
    try:
        from notifications import get_notifier
    except ImportError:
        print(f"\n[邮件通知] 通知模块未安装，无法发送通知")
        return
    
    try:
        # 目前只支持邮件通知
        notifier = get_notifier('email')
        if not notifier or not notifier.is_available():
            print(f"\n[邮件通知] 服务不可用，请检查配置")
            return
        
        # 收件人优先从命令行参数获取，如果没有指定则从配置文件读取
        if args.notify_to:
            recipients = args.notify_to
        else:
            recipients = config.EMAIL_CONFIG['default_recipients']
        
        # 防骚扰检查
        filtered_recipients, throttle_manager = check_notification_throttle(args, selector, recipients)
        if filtered_recipients is None:
            return  # 防骚扰检查未通过
        
        recipients = filtered_recipients
        if not args.notify_throttle:
            print(f"[邮件通知] 使用收件人: {recipients}")
        
        # 构建通知内容
        subject = f"A股选股程序执行结果 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        body = build_notification_body(args, results, selector)
        
        # 准备股票数据
        stock_data, total_stocks_count = prepare_stock_data_for_notification(results)
        
        # 调试信息：显示实际分析的总股票数和返回的股票数
        if total_stocks_count > 0:
            print(f"[邮件通知] 实际分析股票总数: {total_stocks_count} 只，返回TOP股票: {len(results)} 只")
        
        # 发送通知
        success = notifier.send_notification(subject, body, recipients, 
                                            stock_data=stock_data, 
                                            total_stocks=total_stocks_count)
        if success:
            print(f"\n[邮件通知] 已发送通知到: {', '.join(recipients)}")
            
            # 如果启用了防骚扰模式，标记已发送的邮箱地址
            if args.notify_throttle and throttle_manager:
                for email in recipients:
                    throttle_manager.mark_as_sent(email)
        else:
            print(f"\n[邮件通知] 发送失败，请检查邮件配置")
    
    except Exception as e:
        print(f"\n[邮件通知] 发送出错: {e}")
        print(f"[提示] 请检查邮件配置或网络连接")


def _handle_interrupt(selector: StockSelector):
    """处理用户中断（Ctrl+C）"""
    print("\n" + "=" * 60)
    print("程序被用户中断（Ctrl+C）")
    print("=" * 60)
    try:
        saved_count = selector.strategy.data_fetcher.flush_batch_cache()
        if saved_count > 0:
            print(f"[缓存更新] 已保存 {saved_count} 只股票的缓存数据")
        print("[提示] 已保存的数据将在下次运行时继续使用，无需重新下载")
    except Exception as cache_error:
        print(f"[警告] 保存缓存失败: {cache_error}")
    print("=" * 60)


def _handle_execution_error(selector: StockSelector, error: Exception):
    """处理执行错误"""
    print(f"\n程序执行出错: {error}")
    try:
        saved_count = selector.strategy.data_fetcher.flush_batch_cache()
        if saved_count > 0:
            print(f"[缓存更新] 已保存 {saved_count} 只股票的缓存数据")
    except Exception as cache_error:
        print(f"[警告] 保存缓存失败: {cache_error}")
    raise


def _create_strategy(args) -> BaseStrategy:
    """
    根据参数创建多因子策略实例（根据因子组合选择不同的策略实现）
    Args:
        args: 命令行参数对象
    Returns:
        策略实例
    """
    # 多因子策略的不同因子组合
    factor_set_map = {
        'fundamental': lambda: ScoringStrategy(force_refresh=args.refresh, test_sources=False),
        'index_weight': lambda: _create_index_weight_strategy(args),
    }
    
    if args.strategy != 'multi_factor':
        print(f"错误: 目前仅支持 multi_factor 策略")
        sys.exit(1)
    
    if args.factor_set not in factor_set_map:
        print(f"错误: 未知的因子组合: {args.factor_set}")
        print(f"支持的因子组合: {', '.join(factor_set_map.keys())}")
        sys.exit(1)
    
    return factor_set_map[args.factor_set]()


def _create_index_weight_strategy(args) -> BaseStrategy:
    """创建指数权重策略实例"""
    from strategies.index_weight_strategy import IndexWeightStrategy
    return IndexWeightStrategy(
        force_refresh=args.refresh,
        test_sources=False,
        index_codes=args.indices if args.indices else None,
        lookback_days=args.lookback_days
    )


def _prepare_select_params(args, strategy: BaseStrategy) -> dict:
    """
    准备选股参数，根据因子组合设置默认值
    Args:
        args: 命令行参数对象
        strategy: 策略实例
    Returns:
        选股参数字典
    """
    # 根据因子组合设置board参数的默认值
    board_types = args.board
    if board_types is None:
        if args.factor_set == 'index_weight':
            # 指数权重因子组合：不指定board时，使用所有板块（None表示所有板块）
            board_types = None
        else:
            # 其他因子组合：不指定board时，使用默认配置（主板）
            board_types = config.DEFAULT_BOARD_TYPES
    
    # 基础参数
    params = {
        'stock_codes': args.stocks,
        'top_n': args.top_n,
        'board_types': board_types,
        'max_workers': args.workers,
    }
    
    # 指数权重因子组合的额外参数
    if args.factor_set == 'index_weight':
        params.update({
            'index_codes': args.indices,
            'lookback_days': args.lookback_days,
        })
    
    return params


def _print_startup_info(args, strategy: BaseStrategy):
    """打印启动信息"""
    if args.factor_set == 'fundamental':
        print_status_info()
    if args.refresh:
        print("  强制刷新模式：将重新获取所有数据")


def _execute_selection(selector: StockSelector, strategy: BaseStrategy, params: dict) -> pd.DataFrame:
    """
    执行选股
    Args:
        selector: 选股器实例
        strategy: 策略实例
        params: 选股参数字典
    Returns:
        选股结果DataFrame
    """
    # 指数权重因子组合直接使用策略的select_top_stocks方法（支持额外参数）
    if strategy.get_strategy_name() == 'IndexWeightStrategy':
        return strategy.select_top_stocks(**params)
    else:
        # 其他因子组合使用选股器的select_top_stocks方法
        return selector.select_top_stocks(**params)


def main():
    """主函数"""
    import argparse
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='A股选股程序 - 支持多策略')
    parser.add_argument('--refresh', action='store_true', help='强制刷新缓存')
    parser.add_argument('--strategy', type=str, default='multi_factor',
                       choices=['multi_factor'],
                       help='选股策略（目前仅支持多因子策略）')
    parser.add_argument('--factor-set', type=str, default='combined',
                       choices=['fundamental', 'index_weight', 'combined'],
                       help='因子组合 (fundamental: 基本面+成交量+价格因子, index_weight: 指数权重变化趋势因子, combined: 同时运行两个策略)')
    parser.add_argument('--top-n', type=int, default=config.TOP_N, help='返回前N只股票')
    parser.add_argument('--stocks', type=str, nargs='+', help='指定股票代码列表')
    parser.add_argument('--cache-info', type=str, help='查看指定股票的缓存数据详情')
    parser.add_argument('--board', type=str, nargs='+', 
                       choices=['main', 'sme', 'gem', 'star', 'bse', 'b'],
                       default=None,
                       help='板块类型：main(主板), sme(中小板), gem(创业板), star(科创板), bse(北交所), b(B股)。不指定时：fundamental因子组合默认使用主板，index_weight因子组合默认使用所有板块')
    parser.add_argument('--workers', type=int, default=config.DEFAULT_MAX_WORKERS, help='线程数')
    
    # 指数权重因子组合专用参数
    parser.add_argument('--indices', type=str, nargs='+',
                       help='指定要追踪的指数代码列表（仅用于index_weight因子组合），如：000300.SH 000905.SH')
    parser.add_argument('--lookback-days', type=int, default=None,
                       help='回看天数（用于计算权重趋势，仅用于index_weight因子组合）')
    
    parser.add_argument('--notify', action='store_true',
                       help='启用邮件通知功能（收件人从 config.py 的 EMAIL_CONFIG[\'default_recipients\'] 读取）')
    parser.add_argument('--notify-to', type=str, nargs='+',
                       help='指定邮件通知的收件人邮箱列表（可指定多个），如：--notify-to email1@example.com email2@example.com。如果不指定，则使用 config.py 中的 default_recipients')
    parser.add_argument('--notify-throttle', action='store_true', 
                       help='启用通知防骚扰：仅在交易日15:00之后发送，且每个邮箱每天最多发送一次')
    args = parser.parse_args()

    # 处理缓存信息查询
    if args.cache_info:
        print_cache_info(args.cache_info)
        return

    # 前置检查：验证Tushare Token配置
    if not check_tushare_token():
        sys.exit(1)
    
    # 创建并执行选股流程
    try:
        # 如果使用combined模式，同时运行两个策略
        if args.factor_set == 'combined':
            # 运行两个策略
            print("\n" + "=" * 60)
            print("【综合策略模式】同时运行两个策略")
            print("=" * 60)
            
            # 创建两个策略的参数副本
            args_fundamental = argparse.Namespace(**vars(args))
            args_fundamental.factor_set = 'fundamental'
            args_index_weight = argparse.Namespace(**vars(args))
            args_index_weight.factor_set = 'index_weight'
            
            # 运行基本面策略
            print("\n" + "-" * 60)
            print("【策略1】多因子打分策略（基本面+成交量+价格）")
            print("-" * 60)
            strategy_fundamental = _create_strategy(args_fundamental)
            selector_fundamental = StockSelector(strategy=strategy_fundamental)
            select_params_fundamental = _prepare_select_params(args_fundamental, strategy_fundamental)
            _print_startup_info(args_fundamental, strategy_fundamental)
            results_fundamental = _execute_selection(selector_fundamental, strategy_fundamental, select_params_fundamental)
            
            # 运行指数权重策略
            print("\n" + "-" * 60)
            print("【策略2】指数权重选股策略")
            print("-" * 60)
            strategy_index_weight = _create_strategy(args_index_weight)
            selector_index_weight = StockSelector(strategy=strategy_index_weight)
            select_params_index_weight = _prepare_select_params(args_index_weight, strategy_index_weight)
            _print_startup_info(args_index_weight, strategy_index_weight)
            results_index_weight = _execute_selection(selector_index_weight, strategy_index_weight, select_params_index_weight)
            
            # 输出结果
            print("\n" + "=" * 60)
            print("【策略1结果】多因子打分策略")
            print("=" * 60)
            print_results(results_fundamental, selector_fundamental)
            
            print("\n" + "=" * 60)
            print("【策略2结果】指数权重选股策略")
            print("=" * 60)
            print_results(results_index_weight, selector_index_weight)
            
            # 发送通知（合并两个策略的结果）
            if args.notify:
                _send_combined_notification(args, results_fundamental, results_index_weight, 
                                          selector_fundamental, selector_index_weight)
        else:
            # 单个策略模式（原有逻辑）
            strategy = _create_strategy(args)
            selector = StockSelector(strategy=strategy)
            
            # 准备选股参数
            select_params = _prepare_select_params(args, strategy)
            
            # 打印状态信息
            _print_startup_info(args, strategy)
            
            # 执行选股
            results = _execute_selection(selector, strategy, select_params)
            
            # 输出结果
            print_results(results, selector)
            
            # 发送通知
            if args.notify:
                _send_notification(args, results, selector)
            
    except KeyboardInterrupt:
        _handle_interrupt(selector)
        return
    except Exception as e:
        _handle_execution_error(selector, e)


if __name__ == '__main__':
    main()
