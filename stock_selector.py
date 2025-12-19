"""
A股选股程序主程序 - 支持多策略和缓存管理
"""
# 修复Windows中文编码问题
import fix_encoding

import pandas as pd
from datetime import datetime
from typing import List, Optional, Dict
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
    
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "A股选股程序 - 打分策略" + " " * 19 + "║")
    print("╚" + "═" * 58 + "╝")
    
    in_trading = is_trading_time()
    use_yesterday = should_use_yesterday_data()
    
    print("\n【运行状态】")
    if in_trading:
        print("  当前状态：交易中，使用昨天收盘后的完整数据进行分析")
    elif use_yesterday:
        print("  当前状态：非交易时间，使用最近一个交易日的完整数据进行分析")
    else:
        print("  当前状态：收盘后，使用今天收盘后的完整数据进行分析")


def _calculate_data_availability(results: pd.DataFrame) -> Dict[str, Dict[str, int]]:
    """
    计算数据可用性统计
    Args:
        results: 评估结果DataFrame
    Returns:
        数据可用性统计字典
    """
    availability = {
        '基本面': {'available': 0, 'total': 0},
        '财务': {'available': 0, 'total': 0},
        '价格': {'available': 0, 'total': 0},
        '成交量': {'available': 0, 'total': 0},
    }

    for _, row in results.iterrows():
        # 统计基本面数据可用性（至少有PE或PB之一）
        availability['基本面']['total'] += 1
        pe_ratio = row.get('pe_ratio')
        pb_ratio = row.get('pb_ratio')
        if pe_ratio is not None or pb_ratio is not None:
            availability['基本面']['available'] += 1

        # 统计财务数据可用性（有ROE）
        availability['财务']['total'] += 1
        roe = row.get('roe')
        if roe is not None:
            availability['财务']['available'] += 1

        # 统计价格数据可用性（有price_score且不为0）
        availability['价格']['total'] += 1
        price_score = row.get('price_score')
        if price_score is not None and price_score != 0:
            availability['价格']['available'] += 1

        # 统计成交量数据可用性（有volume_score且不为0）
        availability['成交量']['total'] += 1
        volume_score = row.get('volume_score')
        if volume_score is not None and volume_score != 0:
            availability['成交量']['available'] += 1

    return availability


def _print_top5_details(results: pd.DataFrame, selector: StockSelector):
    """打印TOP5股票的详细指标信息"""
    if len(results) == 0:
        return

    # 获取TOP5股票
    top5 = results.head(5)

    print("\n" + "═" * 60)
    print("【TOP5股票详细指标】")
    print("═" * 60)

    for idx, (_, stock) in enumerate(top5.iterrows(), 1):
        code = stock.get('code', 'N/A')
        name = stock.get('name', 'N/A')

        print(f"\n【第{idx}名】{code} {name}")
        print("-" * 40)

        # 基本面评分详情
        _print_fundamental_details(stock)

        # 成交量评分详情
        _print_volume_details(stock)

        # 价格评分详情
        _print_price_details(stock)

        # 最终得分计算
        _print_final_score_calculation(stock, selector)


def _print_fundamental_details(stock: pd.Series):
    """打印基本面指标详情"""
    print("【基本面评分详情】")

    # 获取原始数据
    pe_ratio = stock.get('pe_ratio')
    pb_ratio = stock.get('pb_ratio')
    roe = stock.get('roe')
    revenue_growth = stock.get('revenue_growth')
    profit_growth = stock.get('profit_growth')

    fundamental_weights = config.FUNDAMENTAL_WEIGHTS
    scores = {}

    # 计算各子指标得分
    # 1. PE评分
    if pe_ratio is not None and pe_ratio > 0:
        if pe_ratio <= 20:
            pe_score = 100
        elif pe_ratio <= 30:
            pe_score = 80
        elif pe_ratio <= 50:
            pe_score = 60
        else:
            pe_score = max(0, 60 - (pe_ratio - 50) * 2)
        scores['pe_ratio'] = pe_score
        print(f"  PE市盈率 {pe_ratio:.2f}: {pe_score}分 (估值{'合理' if pe_ratio <= 30 else '较高'})")
    elif pe_ratio == 0:
        scores['pe_ratio'] = 40
        print("  PE市盈率 0.00: 40分 (亏损股)")
    else:
        scores['pe_ratio'] = 50
        print("  PE市盈率: 无数据 (50分 默认值)")

    # 2. PB评分
    if pb_ratio is not None and pb_ratio > 0:
        if pb_ratio <= 1:
            pb_score = 100
        elif pb_ratio <= 2:
            pb_score = 80
        elif pb_ratio <= 3:
            pb_score = 60
        elif pb_ratio <= 5:
            pb_score = 40
        else:
            pb_score = max(0, 40 - (pb_ratio - 5) * 5)
        scores['pb_ratio'] = pb_score
        print(f"  PB市净率 {pb_ratio:.2f}: {pb_score}分 ({'低估' if pb_ratio <= 1.5 else '合理' if pb_ratio <= 2.5 else '高估'})")
    elif pb_ratio == 0:
        scores['pb_ratio'] = 40
        print("  PB市净率 0.00: 40分 (特殊情况)")
    else:
        scores['pb_ratio'] = 50
        print("  PB市净率: 无数据 (50分 默认值)")

    # 3. ROE评分
    if roe is not None and roe != 0:
        if roe >= 20:
            roe_score = 100
        elif roe >= 15:
            roe_score = 85
        elif roe >= 10:
            roe_score = 70
        elif roe >= 5:
            roe_score = 50
        else:
            roe_score = max(0, 50 + roe * 2)
        scores['roe'] = roe_score
        roe_desc = "优秀" if roe >= 15 else "良好" if roe >= 10 else "一般" if roe >= 5 else "较差"
        print(f"  ROE净资产收益率 {roe:.2f}%: {roe_score}分 ({roe_desc})")
    else:
        scores['roe'] = 50
        print("  ROE净资产收益率: 无数据 (50分 默认值)")

    # 4. 营收增长率评分
    if revenue_growth is not None:
        if revenue_growth >= 50:
            rev_score = 100
        elif revenue_growth >= 30:
            rev_score = 85
        elif revenue_growth >= 15:
            rev_score = 70
        elif revenue_growth >= 0:
            rev_score = 50
        else:
            rev_score = max(0, 50 + revenue_growth)
        scores['revenue_growth'] = rev_score
        growth_desc = "高速增长" if revenue_growth >= 30 else "稳步增长" if revenue_growth >= 15 else "缓慢增长" if revenue_growth >= 0 else "负增长"
        print(f"  营收增长率 {revenue_growth:.2f}%: {rev_score}分 ({growth_desc})")
    else:
        scores['revenue_growth'] = 50

    # 5. 利润增长率评分
    if profit_growth is not None:
        if profit_growth >= 50:
            prof_score = 100
        elif profit_growth >= 30:
            prof_score = 85
        elif profit_growth >= 15:
            prof_score = 70
        elif profit_growth >= 0:
            prof_score = 50
        else:
            prof_score = max(0, 50 + profit_growth)
        scores['profit_growth'] = prof_score
        growth_desc = "高速增长" if profit_growth >= 30 else "稳步增长" if profit_growth >= 15 else "缓慢增长" if profit_growth >= 0 else "负增长"
        print(f"  利润增长率 {profit_growth:.2f}%: {prof_score}分 ({growth_desc})")
    else:
        scores['profit_growth'] = 50

    # 计算加权得分
    fundamental_score = sum(scores.get(key, 50) * fundamental_weights.get(key, 0)
                           for key in fundamental_weights.keys())
    fundamental_score = min(100, max(0, fundamental_score))

    print("  基本面子维度权重计算:")
    for key, weight in fundamental_weights.items():
        if weight > 0:
            sub_score = scores.get(key, 50)
            contribution = sub_score * weight
            sub_name = {
                'pe_ratio': 'PE',
                'pb_ratio': 'PB',
                'roe': 'ROE',
                'revenue_growth': '营收增长',
                'profit_growth': '利润增长'
            }.get(key, key)
            print(f"    {sub_name}: {sub_score}分 × {weight*100:.1f}% = {contribution:.2f}")

    print(f"  基本面综合得分: {fundamental_score:.2f}")


def _print_volume_details(stock: pd.Series):
    """打印成交量指标详情"""
    print("\n【成交量评分详情】")

    volume_weights = config.VOLUME_WEIGHTS

    # 获取详细指标数据
    volume_ratio = stock.get('volume_ratio')
    turnover_rate = stock.get('turnover_rate')
    volume_trend = stock.get('volume_trend')

    # 获取各子维度得分
    volume_ratio_score = stock.get('volume_ratio_score', 50)
    turnover_rate_score = stock.get('turnover_rate_score', 50)
    volume_trend_score = stock.get('volume_trend_score', 50)

    scores = {}

    # 1. 量比评分详情
    if volume_ratio is not None:
        scores['volume_ratio'] = volume_ratio_score
        volume_desc = "放量" if volume_ratio >= 2 else "适中" if volume_ratio >= 1 else "缩量"
        print(f"  量比 {volume_ratio:.2f}: {volume_ratio_score}分 ({volume_desc})")
    else:
        scores['volume_ratio'] = 50
        print("  量比: 无数据 (50分 默认值)")

    # 2. 换手率评分详情
    if turnover_rate is not None:
        scores['turnover_rate'] = turnover_rate_score
        turnover_desc = "高换手" if turnover_rate >= 10 else "适中换手" if turnover_rate >= 3 else "低换手"
        print(f"  换手率 {turnover_rate:.2f}%: {turnover_rate_score}分 ({turnover_desc})")
    else:
        scores['turnover_rate'] = 50
        print("  换手率: 无数据 (50分 默认值)")

    # 3. 成交量趋势评分详情
    if volume_trend is not None:
        scores['volume_trend'] = volume_trend_score
        trend_desc = "放量上涨" if volume_trend >= 1.2 else "温和放量" if volume_trend >= 1.1 else "缩量" if volume_trend < 0.9 else "平稳"
        print(f"  成交量趋势 {volume_trend:.3f}: {volume_trend_score}分 ({trend_desc})")
    else:
        scores['volume_trend'] = 50
        print("  成交量趋势: 无数据 (50分 默认值)")

    # 计算加权得分
    volume_score = sum(scores.get(key, 50) * volume_weights.get(key, 0)
                      for key in volume_weights.keys())
    volume_score = min(100, max(0, volume_score))

    print("  成交量子维度权重计算:")
    for key, weight in volume_weights.items():
        if weight > 0:
            sub_score = scores.get(key, 50)
            contribution = sub_score * weight
            sub_name = {
                'volume_ratio': '量比',
                'turnover_rate': '换手率',
                'volume_trend': '成交量趋势'
            }.get(key, key)
            print(f"    {sub_name}: {sub_score}分 × {weight*100:.1f}% = {contribution:.2f}")

    print(f"  成交量综合得分: {volume_score:.2f}")


def _print_price_details(stock: pd.Series):
    """打印价格指标详情"""
    print("\n【价格评分详情】")

    price_weights = config.PRICE_WEIGHTS

    # 获取详细指标数据
    price_trend = stock.get('price_trend')
    price_position = stock.get('price_position')
    volatility = stock.get('volatility')

    # 获取各子维度得分
    price_trend_score = stock.get('price_trend_score', 50)
    price_position_score = stock.get('price_position_score', 50)
    volatility_score = stock.get('volatility_score', 50)

    scores = {}

    # 1. 价格趋势评分详情
    if price_trend is not None:
        scores['price_trend'] = price_trend_score
        if price_trend >= 1.05:
            trend_desc = "强势上涨"
        elif price_trend >= 1.02:
            trend_desc = "温和上涨"
        elif price_trend >= 1.0:
            trend_desc = "震荡上行"
        elif price_trend >= 0.98:
            trend_desc = "震荡下行"
        else:
            trend_desc = "下跌趋势"
        trend_pct = (price_trend - 1) * 100
        print(f"  价格趋势 {trend_pct:+.2f}%: {price_trend_score}分 ({trend_desc})")
    else:
        scores['price_trend'] = 50
        print("  价格趋势: 无数据 (50分 默认值)")

    # 2. 价格位置评分详情
    if price_position is not None:
        scores['price_position'] = price_position_score
        position_pct = price_position * 100
        if 30 <= position_pct <= 70:
            position_desc = "适中位置"
        elif 20 <= position_pct < 30 or 70 < position_pct <= 80:
            position_desc = "较高位置"
        elif 10 <= position_pct < 20 or 80 < position_pct <= 90:
            position_desc = "很高位置"
        else:
            position_desc = "极高/极低位置"
        print(f"  价格位置 {position_pct:.1f}%: {price_position_score}分 ({position_desc})")
    else:
        scores['price_position'] = 50
        print("  价格位置: 无数据 (50分 默认值)")

    # 3. 波动率评分详情
    if volatility is not None:
        scores['volatility'] = volatility_score
        vol_pct = volatility * 100
        if 20 <= vol_pct <= 40:
            vol_desc = "适度波动"
        elif 15 <= vol_pct < 20 or 40 < vol_pct <= 50:
            vol_desc = "较高波动"
        elif 10 <= vol_pct < 15 or 50 < vol_pct <= 60:
            vol_desc = "很高波动"
        else:
            vol_desc = "极高/极低波动"
        print(f"  波动率 {vol_pct:.2f}%: {volatility_score}分 ({vol_desc})")
    else:
        scores['volatility'] = 50
        print("  波动率: 无数据 (50分 默认值)")

    # 计算加权得分
    price_score = sum(scores.get(key, 50) * price_weights.get(key, 0)
                     for key in price_weights.keys())
    price_score = min(100, max(0, price_score))

    print("  价格子维度权重计算:")
    for key, weight in price_weights.items():
        if weight > 0:
            sub_score = scores.get(key, 50)
            contribution = sub_score * weight
            sub_name = {
                'price_trend': '价格趋势',
                'price_position': '价格位置',
                'volatility': '波动率'
            }.get(key, key)
            print(f"    {sub_name}: {sub_score}分 × {weight*100:.1f}% = {contribution:.2f}")

    print(f"  价格综合得分: {price_score:.2f}")


def _print_final_score_calculation(stock: pd.Series, selector: StockSelector):
    """打印最终得分计算"""
    print("\n【最终得分计算】")

    fundamental_score = stock.get('fundamental_score', 0)
    volume_score = stock.get('volume_score', 0)
    price_score = stock.get('price_score', 0)
    total_score = stock.get('score', 0)

    # 获取实际使用的权重
    actual_weights = getattr(selector.strategy, '_last_adjusted_weights', selector.strategy.weights)

    print("  三大维度权重配置:")
    for dim_key, weight in actual_weights.items():
        if weight > 0:
            dim_name = {
                'fundamental': '基本面',
                'volume': '成交量',
                'price': '价格'
            }.get(dim_key, dim_key)
            print(f"    {dim_name}: {weight*100:.1f}%")

    print("\n  三大维度贡献计算:")
    if actual_weights.get('fundamental', 0) > 0:
        contribution = fundamental_score * actual_weights['fundamental']
        print(f"    基本面: {fundamental_score:.2f} × {actual_weights['fundamental']*100:.1f}% = {contribution:.2f}")
    if actual_weights.get('volume', 0) > 0:
        contribution = volume_score * actual_weights['volume']
        print(f"    成交量: {volume_score:.2f} × {actual_weights['volume']*100:.1f}% = {contribution:.2f}")
    if actual_weights.get('price', 0) > 0:
        contribution = price_score * actual_weights['price']
        print(f"    价格: {price_score:.2f} × {actual_weights['price']*100:.1f}% = {contribution:.2f}")

    print(f"\n  综合得分: {total_score:.2f}")

    # 评分等级
    if total_score >= 85:
        grade = "优秀"
    elif total_score >= 75:
        grade = "良好"
    elif total_score >= 65:
        grade = "一般"
    else:
        grade = "较差"

    print(f"  评分等级: {grade}")


def _print_dimension_info(selector: StockSelector):
    """打印评分维度信息"""
    actual_weights = getattr(selector.strategy, '_last_adjusted_weights', selector.strategy.weights)

    dimension_names = {
        'fundamental': '基本面评分',
        'volume': '成交量评分',
        'price': '价格评分',
    }

    dimension_details = {
        'fundamental': ['PE市盈率', 'PB市净率', 'ROE净资产收益率', '营收增长率', '利润增长率'],
        'volume': ['量比', '换手率', '成交量趋势'],
        'price': ['价格趋势', '价格位置', '波动率'],
    }

    used_dimensions = []
    for dim_key, dim_name in dimension_names.items():
        weight = actual_weights.get(dim_key, 0)
        if weight > 0:
            used_dimensions.append(dim_key)

    return used_dimensions, actual_weights, dimension_names, dimension_details


def _print_results(results: pd.DataFrame, selector: StockSelector):
    """打印选股结果"""
    if results.empty:
        print("\n【结果】")
        print("  未找到符合条件的股票")
        return

    # 统计数据可用性
    data_availability = _calculate_data_availability(results)

    # 显示数据可用性
    print("\n" + "═" * 60)
    print("【数据可用性】")
    print("═" * 60)
    for dimension, stats in data_availability.items():
        if stats['total'] > 0:
            percentage = (stats['available'] / stats['total']) * 100
            print(f"  {dimension}: {stats['available']}/{stats['total']} ({percentage:.1f}%)")

    # 显示维度信息
    used_dimensions, actual_weights, dimension_names, dimension_details = _print_dimension_info(selector)

    # 显示评分维度说明
    print("\n" + "═" * 60)
    print("【评分维度说明】")
    print("═" * 60)

    for dim_key in used_dimensions:
        weight = actual_weights.get(dim_key, 0)
        dim_name = dimension_names[dim_key]
        print(f"\n  {dim_name}: {weight*100:.1f}%")
        if dim_key in dimension_details:
            print(f"    子维度: {', '.join(dimension_details[dim_key])}")

    # 显示评分公式
    print("\n【评分公式】")
    print("  总评分 = ", end="")
    score_formula = []
    for dim_key in used_dimensions:
        weight = actual_weights.get(dim_key, 0)
        dim_name = dimension_names[dim_key]
        score_formula.append(f"{dim_name} × {weight*100:.1f}%")
    print(" + ".join(score_formula))

    # 显示TOP股票
    print("\n" + "═" * 60)
    print(f"【TOP {len(results)} 只股票】")
    print("═" * 60)

    # 设置pandas显示选项
    pd.set_option('display.unicode.east_asian_width', True)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', 30)  # 限制列宽以便显示更多列

    # 选择要显示的列
    display_cols = ['code', 'name', 'score', 'fundamental_score', 'volume_score',
                    'price_score']

    available_cols = [col for col in display_cols if col in results.columns]
    print("\n" + results[available_cols].to_string(index=False))
    print("═" * 60)

    # 展示TOP5股票的详细指标信息
    _print_top5_details(results, selector)


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
        print("  强制刷新模式：将重新获取所有数据")
    
    # 创建选股器
    # 优化：Token已在_check_tushare_token()中验证，跳过DataFetcher的重复测试
    strategy = ScoringStrategy(force_refresh=args.refresh, test_sources=False)
    selector = StockSelector(strategy=strategy)

    # 执行选股
    try:
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
