"""
通知辅助函数模块
"""
import pandas as pd
from datetime import datetime
from typing import List, Tuple, Optional
from .throttle_manager import NotificationThrottleManager
from utils.trading_calendar import is_trading_day_after_15_00
import config


def check_notification_throttle(args, selector, recipients):
    """
    检查通知防骚扰条件，过滤收件人列表
    Args:
        args: 命令行参数对象
        selector: StockSelector实例
        recipients: 原始收件人列表
    Returns:
        tuple: (filtered_recipients, throttle_manager) 如果通过检查返回过滤后的收件人列表，否则返回(None, None)
    """
    if not args.notify_throttle:
        return recipients, None
    
    # 检查是否是交易日且在15:00之后
    if not is_trading_day_after_15_00(selector.strategy.data_fetcher):
        print(f"\n[邮件通知] 防骚扰模式已启用")
        print(f"[邮件通知] 当前不在交易日15:00之后，跳过发送通知")
        print(f"[邮件通知] 提示: 使用 --notify-throttle 时，仅在交易日15:00之后发送通知")
        return None, None
    
    # 初始化通知防骚扰管理器
    throttle_manager = NotificationThrottleManager()
    
    # 过滤掉今天已发送过的邮箱地址
    filtered_recipients = []
    for email in recipients:
        if throttle_manager.is_sent_today(email):
            print(f"[邮件通知] 防骚扰: {email} 今天已发送过通知，跳过")
        else:
            filtered_recipients.append(email)
    
    if not filtered_recipients:
        print(f"\n[邮件通知] 防骚扰模式已启用")
        print(f"[邮件通知] 所有收件人今天都已发送过通知，跳过发送")
        return None, None
    
    print(f"[邮件通知] 防骚扰模式已启用，过滤后收件人: {filtered_recipients}")
    return filtered_recipients, throttle_manager


def prepare_stock_data_for_notification(results: pd.DataFrame) -> Tuple[Optional[List[dict]], int]:
    """
    准备通知所需的股票数据
    Args:
        results: 选股结果DataFrame
    Returns:
        tuple: (stock_data, total_stocks_count)
    """
    stock_data = None
    total_stocks_count = 0
    
    if not results.empty:
        # 准备股票数据列表
        stock_data = []
        for _, stock in results.iterrows():
            stock_dict = {
                'code': stock.get('code', 'N/A'),
                'name': stock.get('name', 'N/A'),
                'score': stock.get('score', 0),
                'fundamental_score': stock.get('fundamental_score', 0),
                'volume_score': stock.get('volume_score', 0),
                'price_score': stock.get('price_score', 0),
                'current_price': stock.get('current_price'),
                'pct_change': stock.get('pct_change'),
                'pe_ratio': stock.get('pe_ratio'),
                'pb_ratio': stock.get('pb_ratio'),
                'roe': stock.get('roe'),
                'revenue_growth': stock.get('revenue_growth'),
                'profit_growth': stock.get('profit_growth'),
            }
            stock_data.append(stock_dict)
        
        # 计算总股票数（用于模板）
        if hasattr(results, 'attrs') and 'total_stocks_analyzed' in results.attrs:
            total_stocks_count = results.attrs['total_stocks_analyzed']
        elif hasattr(results, '_total_stocks_analyzed'):
            total_stocks_count = results._total_stocks_analyzed
        else:
            total_stocks_count = len(results)
    
    return stock_data, total_stocks_count


def build_notification_body(args, results: pd.DataFrame, selector):
    """
    构建通知正文内容
    Args:
        args: 命令行参数对象
        results: 选股结果DataFrame
        selector: StockSelector实例
    Returns:
        str: 通知正文内容
    """
    from utils import calculate_data_availability, get_dimension_info
    
    body = f"""
A股选股程序执行完成！

执行参数：
- 策略: {args.strategy}
- TOP-N: {args.top_n}
- 板块: {', '.join(args.board) if args.board else '全部'}
- 强制刷新: {'是' if args.refresh else '否'}

"""
    
    if results.empty:
        body += "未找到符合条件的股票\n"
        return body
    
    # 数据可用性统计
    data_availability = calculate_data_availability(results)
    body += "\n" + "=" * 60 + "\n"
    body += "【数据可用性】\n"
    body += "=" * 60 + "\n"
    for dimension, stats in data_availability.items():
        if stats['total'] > 0:
            percentage = (stats['available'] / stats['total']) * 100
            body += f"  {dimension}: {stats['available']}/{stats['total']} ({percentage:.1f}%)\n"
    
    # 显示维度信息
    used_dimensions, actual_weights, dimension_names, dimension_details = get_dimension_info(selector)
    body += "\n" + "=" * 60 + "\n"
    body += "【评分维度说明】\n"
    body += "=" * 60 + "\n"
    body += f"使用维度: {', '.join(dimension_names)}\n"
    for detail in dimension_details:
        body += f"{detail}\n"
    
    # TOP股票表格
    body += "\n" + "=" * 60 + "\n"
    ranking_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    body += f"【TOP {len(results)} 只股票】 - 排名时间: {ranking_time}\n"
    body += "=" * 60 + "\n\n"
    
    # 选择要显示的列
    display_cols = ['code', 'name', 'score', 'fundamental_score', 'volume_score', 'price_score']
    available_cols = [col for col in display_cols if col in results.columns]
    
    # 将DataFrame转换为字符串格式用于邮件
    table_str = results[available_cols].to_string(index=False)
    body += table_str + "\n"
    body += "=" * 60 + "\n"
    
    # TOP股票详细指标（邮件中只显示前3只，避免邮件过长）
    if len(results) > 0:
        top5 = results.head(min(3, len(results)))
        body += "\n" + "=" * 60 + "\n"
        body += "【TOP股票详细指标】\n"
        body += "=" * 60 + "\n"
        
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
                if hasattr(data_fetch_time, 'strftime'):
                    stock_info += f" | 数据时间: {data_fetch_time.strftime('%Y-%m-%d %H:%M')}"
                else:
                    stock_info += f" | 数据时间: {data_fetch_time}"
            
            body += f"\n{stock_info}\n"
            body += "-" * 60 + "\n"
            
            # 基本面评分详情
            body += "【基本面评分详情】\n"
            pe_ratio = stock.get('pe_ratio')
            pb_ratio = stock.get('pb_ratio')
            roe = stock.get('roe')
            revenue_growth = stock.get('revenue_growth')
            profit_growth = stock.get('profit_growth')
            
            fundamental_weights = config.FUNDAMENTAL_WEIGHTS
            if pe_ratio is not None and pe_ratio > 0:
                body += f"  市盈率(PE): {pe_ratio:.2f} | 权重: {fundamental_weights['pe_ratio']:.0%}\n"
            if pb_ratio is not None and pb_ratio > 0:
                body += f"  市净率(PB): {pb_ratio:.2f} | 权重: {fundamental_weights['pb_ratio']:.0%}\n"
            if roe is not None:
                body += f"  净资产收益率(ROE): {roe:.2f}% | 权重: {fundamental_weights['roe']:.0%}\n"
            if revenue_growth is not None:
                body += f"  营收增长率: {revenue_growth:.2f}% | 权重: {fundamental_weights['revenue_growth']:.0%}\n"
            if profit_growth is not None:
                body += f"  利润增长率: {profit_growth:.2f}% | 权重: {fundamental_weights['profit_growth']:.0%}\n"
            
            # 成交量评分详情
            body += "【成交量评分详情】\n"
            volume_ratio = stock.get('volume_ratio')
            turnover_rate = stock.get('turnover_rate')
            volume_trend = stock.get('volume_trend')
            
            volume_weights = config.VOLUME_WEIGHTS
            if volume_ratio is not None:
                body += f"  量比: {volume_ratio:.2f} | 权重: {volume_weights['volume_ratio']:.0%}\n"
            if turnover_rate is not None:
                body += f"  换手率: {turnover_rate:.2f}% | 权重: {volume_weights['turnover_rate']:.0%}\n"
            if volume_trend is not None:
                body += f"  成交量趋势: {volume_trend:.2f} | 权重: {volume_weights['volume_trend']:.0%}\n"
            
            # 价格评分详情
            body += "【价格评分详情】\n"
            price_trend = stock.get('price_trend')
            price_position = stock.get('price_position')
            volatility = stock.get('volatility')
            
            price_weights = config.PRICE_WEIGHTS
            if price_trend is not None:
                body += f"  价格趋势: {price_trend:.2f} | 权重: {price_weights['price_trend']:.0%}\n"
            if price_position is not None:
                body += f"  价格位置: {price_position:.2f} | 权重: {price_weights['price_position']:.0%}\n"
            if volatility is not None:
                body += f"  波动率: {volatility:.2f} | 权重: {price_weights['volatility']:.0%}\n"
            
            # 最终得分计算
            body += "【最终得分计算】\n"
            fundamental_score = stock.get('fundamental_score', 0)
            volume_score = stock.get('volume_score', 0)
            price_score = stock.get('price_score', 0)
            total_score = stock.get('score', 0)
            
            # 获取实际使用的权重
            actual_weights = getattr(selector.strategy, '_last_adjusted_weights', selector.strategy.weights)
            body += f"  三大维度权重配置:\n"
            body += f"    基本面权重: {actual_weights['fundamental']:.0%} | 得分: {fundamental_score:.2f}\n"
            body += f"    成交量权重: {actual_weights['volume']:.0%} | 得分: {volume_score:.2f}\n"
            body += f"    价格权重: {actual_weights['price']:.0%} | 得分: {price_score:.2f}\n"
            body += f"  综合得分: {total_score:.2f}\n"
    
    return body

