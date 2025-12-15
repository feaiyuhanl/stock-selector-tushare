"""
配置文件：定义评分权重和参数
"""

# 各维度权重配置（总和应为1.0）
WEIGHT_CONFIG = {
    'fundamental': 0.30,      # 基本面权重
    'volume': 0.20,           # 成交量权重
    'price': 0.20,            # 成交价格权重
    'sector': 0.15,           # 关联板块走势权重
    'concept': 0.15,          # 关联概念走势权重
}

# 基本面子维度权重
FUNDAMENTAL_WEIGHTS = {
    'pe_ratio': 0.20,         # 市盈率
    'pb_ratio': 0.20,         # 市净率
    'roe': 0.25,              # 净资产收益率
    'revenue_growth': 0.20,   # 营收增长率
    'profit_growth': 0.15,    # 利润增长率
}

# 成交量子维度权重
VOLUME_WEIGHTS = {
    'volume_ratio': 0.40,     # 量比
    'turnover_rate': 0.30,    # 换手率
    'volume_trend': 0.30,     # 成交量趋势
}

# 价格子维度权重
PRICE_WEIGHTS = {
    'price_trend': 0.35,      # 价格趋势
    'price_position': 0.30,   # 价格位置（相对高低）
    'volatility': 0.35,        # 波动率
}

# 板块/概念走势权重
SECTOR_CONCEPT_WEIGHTS = {
    'sector_trend': 0.50,      # 板块/概念趋势
    'relative_strength': 0.50, # 相对强度
}

# 评分范围
SCORE_MIN = 0
SCORE_MAX = 100

# 选股数量
TOP_N = 20

# 数据获取参数
LOOKBACK_DAYS = 60  # 回看天数

# 板块类型配置
BOARD_TYPES = {
    'main': '主板',      # 默认只选主板
    'sme': '中小板',
    'gem': '创业板',
    'star': '科创板',
    'bse': '北交所',
    'b': 'B股',
}

# 默认板块筛选（只选主板）
DEFAULT_BOARD_TYPES = ['main']  # 可以修改为 ['main', 'gem'] 等

# 多线程配置
DEFAULT_MAX_WORKERS = 10  # 默认线程数

# Tushare配置
TUSHARE_TOKEN = None  # 需要在环境变量或配置文件中设置，或通过代码设置

