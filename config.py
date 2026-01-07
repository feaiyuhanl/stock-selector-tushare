"""
配置文件：定义评分权重和参数
"""

# 各维度权重配置（总和应为1.0）
WEIGHT_CONFIG = {
    'fundamental': 0.40,      # 基本面权重
    'volume': 0.30,           # 成交量权重
    'price': 0.30,            # 成交价格权重
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

# 板块/概念走势权重（已废弃，保留用于兼容性）
# SECTOR_CONCEPT_WEIGHTS = {
#     'sector_trend': 0.50,      # 板块/概念趋势
#     'relative_strength': 0.50, # 相对强度
# }

# 评分范围
SCORE_MIN = 0
SCORE_MAX = 100

# 选股数量
TOP_N = 10

# 数据获取参数
LOOKBACK_DAYS = 60  # 回看天数

# K线数据缓存配置
KLINE_CACHE_RETENTION_DAYS = 250  # K线数据保留天数（约1年，250个交易日）

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

# 邮件通知配置
EMAIL_CONFIG = {
    'enabled': False,  # 是否启用邮件通知
    'default_recipients': ['posterhan@126.com'],  # 默认收件人列表
    'tencent_cloud': {
        'secret_id': None,   # 腾讯云SecretId（可从环境变量TENCENT_SECRET_ID获取）
        'secret_key': None,  # 腾讯云SecretKey（可从环境变量TENCENT_SECRET_KEY获取）
        'region': 'ap-guangzhou',  # 地域
        'from_email': None,  # 发件人邮箱（可从环境变量TENCENT_FROM_EMAIL获取）
        'from_name': 'A股选股程序',  # 发件人名称
        'template_id': 40888,  # 邮件模板ID（如果使用模板发送）
        'use_template': True,  # 是否使用模板发送（True: 使用模板, False: 使用Simple方式）
    }
}

# 企业微信通知配置
WECHAT_CONFIG = {
    'enabled': False,  # 是否启用企业微信通知
    'webhook_url': None,  # 企业微信机器人Webhook URL（可从环境变量WECHAT_WEBHOOK_URL获取）
    # 如何获取Webhook URL:
    # 1. 打开企业微信 -> 应用与小程序
    # 2. 点击右上角"+" -> 机器人
    # 3. 添加机器人并设置Webhook URL
    # 4. 复制Webhook URL配置到环境变量或此处
}

# 指数权重策略配置
INDEX_WEIGHT_CONFIG = {
    # 追踪的指数列表
    'tracked_indices': [
        '000300.SH',  # 沪深300
        '000905.SH',  # 中证500
        '932000.CSI',  # 中证2000（跨市场指数，使用CSI后缀）
    ],
    
    # 指数名称映射
    'index_names': {
        '000300.SH': '沪深300',
        '000905.SH': '中证500',
        '932000.CSI': '中证2000',
    },
    
    # 回看天数（用于计算趋势）
    'lookback_days': 60,
    
    # 评分权重
    'score_weights': {
        'weight_change_rate': 0.50,    # 权重变化率权重
        'trend_slope': 0.30,           # 趋势斜率权重
        'weight_absolute': 0.20,        # 权重绝对值权重
    },
    
    # 多指数加分系数
    'multi_index_bonus': 1.1,  # 在多个指数中都有上升趋势时，得分乘以该系数
    
    # 邮件通知模板ID（指数权重策略专用）
    'email_template_id': 41115,  # 指数权重策略的邮件模板ID
}

