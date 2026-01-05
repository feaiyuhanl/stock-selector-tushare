"""
数据模块工具函数
"""
from datetime import time, datetime, timedelta
from typing import Optional


# 交易时间常量
TRADING_HOURS = {
    'morning_start': time(9, 30),
    'morning_end': time(11, 30),
    'afternoon_start': time(13, 0),
    'afternoon_end': time(15, 0),
}

# 便捷访问
MORNING_START = TRADING_HOURS['morning_start']
MORNING_END = TRADING_HOURS['morning_end']
AFTERNOON_START = TRADING_HOURS['afternoon_start']
AFTERNOON_END = TRADING_HOURS['afternoon_end']


def normalize_stock_code(stock_code: str) -> str:
    """
    标准化股票代码为6位字符串
    Args:
        stock_code: 股票代码（可能是各种格式）
    Returns:
        6位数字字符串
    """
    stock_code = str(stock_code).strip()
    
    # 移除市场后缀（如果有）
    if '.' in stock_code:
        stock_code = stock_code.split('.')[0]
    
    # 确保是6位数字
    if len(stock_code) == 6 and stock_code.isdigit():
        return stock_code
    else:
        # 尝试提取数字部分
        import re
        digits = re.findall(r'\d+', stock_code)
        if digits and len(digits[0]) == 6:
            return digits[0]
    
    # 如果都不行，尝试补零
    return stock_code.zfill(6)


def is_trading_time() -> bool:
    """
    判断当前是否是A股交易时间
    Returns:
        是否在交易时间内
    """
    now = datetime.now()
    current_time = now.time()
    weekday = now.weekday()  # 0=Monday, 6=Sunday
    
    # 周末不交易
    if weekday >= 5:  # Saturday or Sunday
        return False
    
    # 交易时间：上午 9:30-11:30，下午 13:00-15:00
    return (MORNING_START <= current_time <= MORNING_END) or \
           (AFTERNOON_START <= current_time <= AFTERNOON_END)


def get_analysis_date() -> datetime:
    """
    获取用于分析的数据日期
    - 如果当前在交易时间内，使用昨天的数据（今天数据不完整）
    - 如果当前不在交易时间，使用最近一个交易日的数据
    - 如果已经收盘（15:00之后），使用今天的数据
    Returns:
        用于分析的日期
    """
    now = datetime.now()
    current_time = now.time()
    weekday = now.weekday()
    
    # 如果当前在交易时间内，使用昨天的数据（今天数据不完整）
    if is_trading_time():
        # 使用昨天的日期
        analysis_date = now - timedelta(days=1)
        # 如果昨天是周末，继续往前推
        while analysis_date.weekday() >= 5:
            analysis_date = analysis_date - timedelta(days=1)
        return analysis_date
    
    # 如果当前不在交易时间
    # 如果是周末，使用周五的数据
    if weekday >= 5:
        days_back = weekday - 4  # Saturday=1, Sunday=2
        analysis_date = now - timedelta(days=days_back)
    # 如果是工作日但不在交易时间
    else:
        # 如果已经过了15:00，可以使用今天的数据（收盘后）
        if current_time >= AFTERNOON_END:
            analysis_date = now
        # 如果还没到9:30，使用昨天的数据
        elif current_time < MORNING_START:
            analysis_date = now - timedelta(days=1)
            # 如果昨天是周末，继续往前推
            while analysis_date.weekday() >= 5:
                analysis_date = analysis_date - timedelta(days=1)
        # 其他情况（午休时间11:30-13:00），使用昨天的数据
        else:
            analysis_date = now - timedelta(days=1)
            while analysis_date.weekday() >= 5:
                analysis_date = analysis_date - timedelta(days=1)
    
    return analysis_date


def should_use_yesterday_data() -> bool:
    """
    判断是否应该使用昨天的数据进行分析
    - 如果今天还在交易中，使用昨天的完整数据
    - 如果今天还没开盘，使用昨天的数据
    - 如果已经收盘（15:00之后），使用今天的数据
    Returns:
        是否应该使用昨天的数据
    """
    now = datetime.now()
    current_time = now.time()
    weekday = now.weekday()
    
    # 周末使用最近一个交易日的数据（昨天的）
    if weekday >= 5:
        return True
    
    # 如果已经过了15:00，可以使用今天的数据（收盘后）
    if current_time >= AFTERNOON_END:
        return False
    
    # 如果当前在交易时间内，使用昨天的数据（今天数据不完整）
    if is_trading_time():
        return True
    
    # 如果还没到9:30，使用昨天的数据
    if current_time < MORNING_START:
        return True
    
    # 其他情况（午休时间11:30-13:00等），使用昨天的数据
    return True

