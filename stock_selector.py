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
import os
import sys


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
    
    def save_results(self, df: pd.DataFrame, filename: str = None):
        """
        保存结果到文件
        Args:
            df: 结果DataFrame
            filename: 文件名
        """
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            strategy_name = self.strategy.get_strategy_name()
            filename = f'stock_selection_results_{strategy_name}_{timestamp}.xlsx'
        
        if not df.empty:
            try:
                df.to_excel(filename, index=True, engine='openpyxl')
                # 确保文件句柄关闭
                del df
                import time
                time.sleep(0.1)  # 短暂延迟，确保文件句柄释放
                print(f"结果已保存到: {filename}")
            except Exception as e:
                print(f"保存结果失败: {e}")
        else:
            print("没有数据可保存")
    
    def clear_cache(self, cache_type: str = None):
        """
        清除缓存
        Args:
            cache_type: 缓存类型，None表示清除所有
        """
        self.strategy.data_fetcher.cache_manager.clear_cache(cache_type)


def _check_tushare_token():
    """
    检查Tushare Token配置（前置检查）
    Returns:
        bool: Token配置有效返回True，否则返回False
    """
    try:
        import tushare as ts
    except ImportError:
        print("\n" + "=" * 60)
        print("[错误] 未安装tushare包")
        print("=" * 60)
        print("请运行: pip install tushare")
        print("=" * 60)
        return False
    
    # 尝试从环境变量获取
    token = os.environ.get('TUSHARE_TOKEN')
    token_source = "环境变量"
    
    if not token:
        # 从config获取
        if hasattr(config, 'TUSHARE_TOKEN') and config.TUSHARE_TOKEN:
            token = config.TUSHARE_TOKEN
            token_source = "config.py"
    
    if not token:
        print("\n" + "=" * 60)
        print("[错误] 未找到Token配置")
        print("=" * 60)
        print("\n请使用以下方式之一配置Token：")
        print("\n方式1：设置环境变量（推荐）")
        print("  Windows PowerShell:")
        print("    $env:TUSHARE_TOKEN='your_token_here'")
        print("  Windows CMD:")
        print("    set TUSHARE_TOKEN=your_token_here")
        print("  Linux/Mac:")
        print("    export TUSHARE_TOKEN='your_token_here'")
        print("\n方式2：在config.py中设置")
        print("    TUSHARE_TOKEN = 'your_token_here'")
        print("\n方式3：在代码中设置")
        print("    import tushare as ts")
        print("    ts.set_token('your_token_here')")
        print("\n获取Token请访问: https://tushare.pro/register")
        print("=" * 60)
        return False
    
    # 设置Token并测试有效性
    try:
        ts.set_token(token)
        pro = ts.pro_api()
        
        # 测试连接
        test_date = '20241215'
        df = pro.trade_cal(exchange='SSE', start_date=test_date, end_date=test_date)
        
        if df is None or df.empty:
            print("\n" + "=" * 60)
            print("[错误] Token可能无效，返回空结果")
            print("=" * 60)
            print("\n建议：")
            print("1. 登录 https://tushare.pro/ 检查Token和积分")
            print("2. 重新复制最新的Token")
            print("=" * 60)
            return False
        
        # Token有效，继续执行
        return True
        
    except Exception as e:
        error_msg = str(e)
        print("\n" + "=" * 60)
        print(f"[错误] Token配置验证失败: {e}")
        print("=" * 60)
        
        if "权限" in error_msg or "积分" in error_msg or "token" in error_msg.lower():
            print("\n可能的原因：")
            print("1. Token无效或已过期")
            print("2. 积分不足")
            print("3. 权限不足")
            print("\n建议：")
            print("1. 登录 https://tushare.pro/ 检查Token和积分")
            print("2. 重新复制最新的Token")
            print("3. 如果积分不足，需要充值或等待积分恢复")
        else:
            print("\n可能的原因：")
            print("1. 网络连接问题")
            print("2. Tushare服务异常")
            print("3. Token格式错误")
        print("=" * 60)
        return False


def _print_status_info():
    """打印程序状态信息"""
    from data.fetcher import should_use_yesterday_data, is_trading_time
    
    print("=" * 60)
    print("A股选股程序 - 打分策略")
    print("=" * 60)
    
    in_trading = is_trading_time()
    use_yesterday = should_use_yesterday_data()
    
    if in_trading:
        print("当前状态：交易中，使用昨天收盘后的完整数据进行分析")
    elif use_yesterday:
        print("当前状态：非交易时间，使用最近一个交易日的完整数据进行分析")
    else:
        print("当前状态：收盘后，使用今天收盘后的完整数据进行分析")


def _print_dimension_info(selector: StockSelector):
    """打印评分维度信息"""
    actual_weights = getattr(selector.strategy, '_last_adjusted_weights', selector.strategy.weights)
    
    dimension_names = {
        'fundamental': '基本面评分',
        'volume': '成交量评分',
        'price': '价格评分',
        'sector': '板块走势评分',
        'concept': '概念走势评分'
    }
    
    dimension_details = {
        'fundamental': ['PE市盈率', 'PB市净率', 'ROE净资产收益率', '营收增长率', '利润增长率'],
        'volume': ['量比', '换手率', '成交量趋势'],
        'price': ['价格趋势', '价格位置', '波动率'],
        'sector': ['板块趋势', '相对强度'],
        'concept': ['概念趋势', '相对强度']
    }
    
    print("\n【最终打分维度说明】")
    print("-" * 60)
    print("采用的评分维度及权重：")
    
    used_dimensions = []
    for dim_key, dim_name in dimension_names.items():
        weight = actual_weights.get(dim_key, 0)
        if weight > 0:
            used_dimensions.append(dim_key)
            print(f"  ✓ {dim_name}: {weight*100:.1f}%")
            if dim_key in dimension_details:
                print(f"    └─ 子维度: {', '.join(dimension_details[dim_key])}")
    
    # 检查缺失的维度
    missing_dimensions = []
    for dim_key, dim_name in dimension_names.items():
        weight = actual_weights.get(dim_key, 0)
        if weight == 0:
            missing_dimensions.append((dim_key, dim_name))
    
    if missing_dimensions:
        print("\n【缺失指标提示】")
        print("-" * 60)
        for dim_key, dim_name in missing_dimensions:
            print(f"  ⚠ {dim_name}未采用（数据不可用或权重已调整）")
            if dim_key == 'fundamental':
                print("    原因: 基本面数据（PE、PB）缺失或无效")
            elif dim_key == 'sector':
                print("    原因: 板块K线数据缺失或不可用")
            elif dim_key == 'concept':
                print("    原因: 概念K线数据缺失或不可用")
    
    return used_dimensions, actual_weights, dimension_names


def _print_results(results: pd.DataFrame, selector: StockSelector):
    """打印选股结果"""
    if results.empty:
        print("未找到符合条件的股票")
        return
    
    print("\n" + "=" * 60)
    print(f"TOP {len(results)} 只股票:")
    print("=" * 60)
    
    # 显示维度信息
    used_dimensions, actual_weights, dimension_names = _print_dimension_info(selector)
    
    print("\n" + "=" * 60)
    
    # 设置pandas显示选项
    pd.set_option('display.unicode.east_asian_width', True)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', 30)  # 限制列宽以便显示更多列
    
    # 选择要显示的列（包含板块和概念）
    display_cols = ['code', 'name', 'score', 'fundamental_score', 'volume_score', 
                    'price_score', 'sector_score', 'concept_score']
    if 'sectors' in results.columns:
        display_cols.append('sectors')
    if 'concepts' in results.columns:
        display_cols.append('concepts')
    
    available_cols = [col for col in display_cols if col in results.columns]
    print(results[available_cols].to_string(index=False))
    
    # 显示板块趋势涨幅TOP 3
    if hasattr(selector.strategy, '_top_sectors') and selector.strategy._top_sectors:
        print("\n" + "=" * 60)
        print("【板块趋势涨幅TOP 3】")
        print("-" * 60)
        for i, sector_info in enumerate(selector.strategy._top_sectors, 1):
            print(f"{i}. {sector_info['sector']}: 涨幅 {sector_info['trend']:.2f}% "
                  f"(涉及股票: {sector_info['stock_count']}只, 平均评分: {sector_info['avg_score']:.2f})")
        print("=" * 60)
    
    # 显示热点概念
    if hasattr(selector.strategy, '_hot_concepts') and selector.strategy._hot_concepts:
        print("\n" + "=" * 60)
        print("【热点概念TOP 10】")
        print("-" * 60)
        for i, concept_info in enumerate(selector.strategy._hot_concepts, 1):
            print(f"{i}. {concept_info['concept']}: 平均评分 {concept_info['avg_score']:.2f} "
                  f"(涉及股票: {concept_info['stock_count']}只, 热度: {concept_info['hot_score']:.3f})")
        print("=" * 60)
    
    # 显示评分公式
    print("\n" + "=" * 60)
    print("【评分说明】")
    print("-" * 60)
    print("总评分 = ", end="")
    score_formula = []
    for dim_key in used_dimensions:
        weight = actual_weights.get(dim_key, 0)
        dim_name = dimension_names[dim_key]
        score_formula.append(f"{dim_name} × {weight*100:.1f}%")
    print(" + ".join(score_formula))
    print("=" * 60)


def main():
    """主函数"""
    import argparse
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='A股选股程序 - 打分策略')
    parser.add_argument('--refresh', action='store_true', help='强制刷新缓存')
    parser.add_argument('--strategy', type=str, default='scoring', help='选股策略 (scoring)')
    parser.add_argument('--top-n', type=int, default=config.TOP_N, help='返回前N只股票')
    parser.add_argument('--stocks', type=str, nargs='+', help='指定股票代码列表')
    parser.add_argument('--board', type=str, nargs='+', 
                       choices=['main', 'sme', 'gem', 'star', 'bse', 'b'],
                       default=config.DEFAULT_BOARD_TYPES,
                       help='板块类型：main(主板), sme(中小板), gem(创业板), star(科创板), bse(北交所), b(B股)')
    parser.add_argument('--workers', type=int, default=config.DEFAULT_MAX_WORKERS, help='线程数')
    args = parser.parse_args()
    
    # 前置检查：验证Tushare Token配置
    if not _check_tushare_token():
        sys.exit(1)
    
    # 打印状态信息
    _print_status_info()
    if args.refresh:
        print("强制刷新模式：将重新获取所有数据")
    
    # 创建选股器
    strategy = ScoringStrategy(force_refresh=args.refresh)
    selector = StockSelector(strategy=strategy, force_refresh=args.refresh)
    
    # 执行选股
    try:
        print("\n" + "=" * 60)
        print("开始执行选股")
        print("=" * 60)
        
        results = selector.select_top_stocks(
            stock_codes=args.stocks, 
            top_n=args.top_n,
            board_types=args.board,
            max_workers=args.workers
        )
    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("程序被用户中断（Ctrl+C）")
        print("=" * 60)
        try:
            # 保存已获取的缓存数据
            saved_count = selector.strategy.data_fetcher.flush_batch_cache()
            if saved_count > 0:
                print(f"[缓存更新] 已保存 {saved_count} 只股票的缓存数据")
            print("[提示] 已保存的数据将在下次运行时继续使用，无需重新下载")
        except Exception as cache_error:
            print(f"[警告] 保存缓存失败: {cache_error}")
        print("=" * 60)
        return
    except Exception as e:
        print(f"\n程序执行出错: {e}")
        try:
            saved_count = selector.strategy.data_fetcher.flush_batch_cache()
            if saved_count > 0:
                print(f"[缓存更新] 已保存 {saved_count} 只股票的缓存数据")
        except Exception as cache_error:
            print(f"[警告] 保存缓存失败: {cache_error}")
        raise
    
    # 打印结果
    _print_results(results, selector)


if __name__ == '__main__':
    main()
