"""
格式化输出工具函数
"""
import pandas as pd
from datetime import datetime
from typing import Dict, Tuple
import config


# ==================== 数据分析函数 ====================

def calculate_data_availability(results: pd.DataFrame) -> Dict[str, Dict[str, int]]:
    """
    计算数据可用性统计
    Args:
        results: 评估结果DataFrame
    Returns:
        数据可用性统计字典
    """
    # 检查是否是指数权重策略的结果
    is_index_weight = 'index_count' in results.columns or 'weight_change_rate' in results.columns
    
    if is_index_weight:
        # 指数权重策略的数据可用性统计
        availability = {
            '权重数据': {'available': 0, 'total': 0},
            '权重变化率': {'available': 0, 'total': 0},
            '趋势斜率': {'available': 0, 'total': 0},
        }
        
        for _, row in results.iterrows():
            # 统计权重数据可用性
            availability['权重数据']['total'] += 1
            if row.get('index_count', 0) > 0:
                availability['权重数据']['available'] += 1
            
            # 统计权重变化率可用性
            availability['权重变化率']['total'] += 1
            if row.get('weight_change_rate') is not None:
                availability['权重变化率']['available'] += 1
            
            # 统计趋势斜率可用性
            availability['趋势斜率']['total'] += 1
            if row.get('trend_slope') is not None:
                availability['趋势斜率']['available'] += 1
        
        return availability
    else:
        # 打分策略的数据可用性统计
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


def get_dimension_info(selector):
    """
    获取评分维度信息
    Args:
        selector: StockSelector实例
    Returns:
        tuple: (used_dimensions, actual_weights, dimension_names, dimension_details)
    """
    strategy = selector.strategy
    strategy_name = strategy.get_strategy_name()
    
    # 根据策略类型返回不同的维度信息
    if strategy_name == 'IndexWeightStrategy':
        # 指数权重策略的维度信息
        actual_weights = getattr(strategy, 'score_weights', {})
        dimension_names = {
            'weight_change_rate': '权重变化率',
            'trend_slope': '趋势斜率',
            'weight_absolute': '权重绝对值',
        }
        dimension_details = {
            'weight_change_rate': ['权重变化率'],
            'trend_slope': ['趋势斜率'],
            'weight_absolute': ['权重绝对值'],
        }
        used_dimensions = list(dimension_names.keys())
        return used_dimensions, actual_weights, dimension_names, dimension_details
    else:
        # 打分策略的维度信息
        actual_weights = getattr(strategy, '_last_adjusted_weights', getattr(strategy, 'weights', {}))
        
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


# ==================== 格式化打印函数 ====================

def print_cache_info(stock_code: str):
    """
    显示指定股票的所有本地缓存数据信息
    Args:
        stock_code: 股票代码
    """
    try:
        import sqlite3
        from data.cache_manager import CacheManager
        from data.fetcher import DataFetcher
        from utils.token_checker import check_tushare_token

        # 验证Token
        if not check_tushare_token():
            return

        # 格式化股票代码为6位
        stock_code = str(stock_code).zfill(6)
        
        # 创建数据获取器
        data_fetcher = DataFetcher()
        cache_manager = data_fetcher.cache_manager

        print("\n" + "=" * 80)
        print(f"【股票所有缓存数据详情】 - {stock_code}")
        print("=" * 80)

        # 1. 基本面数据缓存信息（显示所有字段）
        print("\n【1. 基本面数据缓存】")
        fundamental_data = cache_manager.get_fundamental(stock_code, force_refresh=False)
        if fundamental_data:
            update_time = fundamental_data.get('update_time', '未知')
            if isinstance(update_time, str):
                try:
                    update_time = datetime.strptime(update_time, '%Y-%m-%d %H:%M:%S')
                except:
                    pass
            print(f"  缓存状态: ✓ 存在")
            print(f"  更新时间: {update_time}")
            print(f"  所有字段:")
            for key, value in fundamental_data.items():
                if key != 'update_time':
                    print(f"    {key}: {value}")
            fundamental_valid = cache_manager._is_cache_valid('fundamental', stock_code)
            print(f"  有效性: {'✓ 有效' if fundamental_valid else '✗ 失效'}")
        else:
            print("  缓存状态: ✗ 不存在")

        # 2. 财务数据缓存信息（显示所有字段）
        print("\n【2. 财务数据缓存】")
        financial_data = cache_manager.get_financial(stock_code, force_refresh=False)
        if financial_data:
            update_time = financial_data.get('update_time', '未知')
            if isinstance(update_time, str):
                try:
                    update_time = datetime.strptime(update_time, '%Y-%m-%d %H:%M:%S')
                except:
                    pass
            print(f"  缓存状态: ✓ 存在")
            print(f"  更新时间: {update_time}")
            print(f"  所有字段:")
            for key, value in financial_data.items():
                if key != 'update_time':
                    print(f"    {key}: {value}")
            financial_valid = cache_manager._is_cache_valid('financial', stock_code)
            print(f"  有效性: {'✓ 有效' if financial_valid else '✗ 失效'}")
        else:
            print("  缓存状态: ✗ 不存在")

        # 3. K线数据缓存信息（显示详细信息）
        print("\n【5. K线数据缓存】")
        kline_data = cache_manager.get_kline(stock_code, 'stock', 'daily', force_refresh=False)
        if kline_data is not None and not kline_data.empty:
            print(f"  缓存状态: ✓ 存在")
            print(f"  数据条数: {len(kline_data)}")
            print(f"  时间范围: {kline_data['date'].min()} ~ {kline_data['date'].max()}")
            if not kline_data.empty:
                latest_data = kline_data.iloc[-1]
                print(f"  最新交易日数据:")
                for col in kline_data.columns:
                    value = latest_data.get(col)
                    if value is not None:
                        print(f"    {col}: {value}")
                # 显示前5条和后5条数据
                print(f"  前5条数据:")
                print(kline_data.head(5).to_string())
                print(f"  后5条数据:")
                print(kline_data.tail(5).to_string())
            kline_valid = cache_manager.has_latest_trading_day_data(stock_code, 'stock', 'daily')
            print(f"  有效性: {'✓ 有效' if kline_valid else '✗ 失效'}")
        else:
            print("  缓存状态: ✗ 不存在")

        # 4. 指数权重数据缓存信息
        print("\n【4. 指数权重数据缓存】")
        index_codes = ['000300.SH', '000905.SH', '932000.CSI']
        for index_code in index_codes:
            weight_data = cache_manager.get_index_weight(index_code, force_refresh=False)
            if weight_data is not None and not weight_data.empty:
                # 检查该股票是否在指数中
                stock_in_index = weight_data[weight_data['con_code'] == stock_code]
                if not stock_in_index.empty:
                    latest_weight = stock_in_index.iloc[-1]['weight']
                    print(f"  {index_code}: ✓ 存在，权重 {latest_weight:.4f}%")
                else:
                    print(f"  {index_code}: ✗ 该股票不在指数中")
            else:
                print(f"  {index_code}: ✗ 无缓存数据")

        print("\n" + "=" * 80)

    except Exception as e:
        print(f"\n显示缓存信息失败: {e}")
        import traceback
        traceback.print_exc()


def print_status_info():
    """打印程序状态信息"""
    from data import should_use_yesterday_data, is_trading_time
    
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


def print_fundamental_details(stock: pd.Series):
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


def print_volume_details(stock: pd.Series):
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


def print_price_details(stock: pd.Series):
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


def print_final_score_calculation(stock: pd.Series, selector):
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


def print_top5_details(results: pd.DataFrame, selector):
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

        # 获取数据获取时间、收盘价、涨跌幅
        current_price = stock.get('current_price')
        pct_change = stock.get('pct_change')
        data_fetch_time = stock.get('data_fetch_time')

        # 构建股票信息字符串
        stock_info = f"【第{idx}名】{code} {name}"

        # 添加价格信息
        if current_price is not None:
            stock_info += f" | 收盘价: {current_price:.2f}元"
        if pct_change is not None:
            stock_info += f" | 涨跌幅: {pct_change:+.2f}%"
        if data_fetch_time is not None:
            # 如果是datetime对象，格式化显示
            if hasattr(data_fetch_time, 'strftime'):
                stock_info += f" | 数据时间: {data_fetch_time.strftime('%Y-%m-%d %H:%M')}"
            else:
                stock_info += f" | 数据时间: {data_fetch_time}"

        print(f"\n{stock_info}")
        print("-" * 60)

        # 基本面评分详情
        print_fundamental_details(stock)

        # 成交量评分详情
        print_volume_details(stock)

        # 价格评分详情
        print_price_details(stock)

        # 最终得分计算
        print_final_score_calculation(stock, selector)


def print_results(results: pd.DataFrame, selector):
    """打印选股结果"""
    if results.empty:
        print("\n【结果】")
        print("  未找到符合条件的股票")
        return

    # 统计数据可用性
    data_availability = calculate_data_availability(results)

    # 显示数据可用性
    print("\n" + "═" * 60)
    print("【数据可用性】")
    print("═" * 60)
    for dimension, stats in data_availability.items():
        if stats['total'] > 0:
            percentage = (stats['available'] / stats['total']) * 100
            print(f"  {dimension}: {stats['available']}/{stats['total']} ({percentage:.1f}%)")

    # 显示维度信息
    used_dimensions, actual_weights, dimension_names, dimension_details = get_dimension_info(selector)

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

    # 设置pandas显示选项
    pd.set_option('display.unicode.east_asian_width', True)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', 30)  # 限制列宽以便显示更多列

    # 选择要显示的列（根据策略类型）
    strategy_name = selector.strategy.get_strategy_name()
    if strategy_name == 'IndexWeightStrategy':
        display_cols = ['code', 'name', 'score', 'index_count', 'weight_change_rate', 
                       'trend_slope', 'latest_weight']
    else:
        display_cols = ['code', 'name', 'score', 'fundamental_score', 'volume_score',
                       'price_score']

    available_cols = [col for col in display_cols if col in results.columns]
    
    # 检查是否有category列（分类选股结果）
    ranking_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if 'category' in results.columns:
        # 按分类分开展示
        categories = results['category'].unique()
        
        for category in categories:
            category_results = results[results['category'] == category]
            
            print("\n" + "═" * 60)
            print(f"【{category} TOP {len(category_results)} 只股票】 - 排名时间: {ranking_time}")
            print("═" * 60)
            
            # 准备显示的列（排除category列）
            display_cols_without_category = [col for col in available_cols if col != 'category']
            
            # 重置索引以便显示
            category_results_display = category_results[display_cols_without_category].copy()
            category_results_display.reset_index(drop=True, inplace=True)
            category_results_display.index = category_results_display.index + 1  # 从1开始编号
            
            print("\n" + category_results_display.to_string())
            print("═" * 60)
    else:
        # 原有的单表格展示方式
        print("\n" + "═" * 60)
        print(f"【TOP {len(results)} 只股票】 - 排名时间: {ranking_time}")
        print("═" * 60)
        print("\n" + results[available_cols].to_string(index=False))
        print("═" * 60)

    # 展示TOP5股票的详细指标信息（仅对打分策略）
    if strategy_name != 'IndexWeightStrategy':
        print_top5_details(results, selector)

