# 参数配置说明

本文档说明程序的各种参数配置，包括权重配置、命令行参数、板块配置等。

## 目录

- [权重配置](#权重配置)
- [命令行参数](#命令行参数)
- [板块类型配置](#板块类型配置)
- [数据获取参数](#数据获取参数)
- [通知配置](#通知配置)
- [指数权重策略配置](#指数权重策略配置)

---

## 权重配置

权重配置位于 `config.py` 文件中，用于控制各评分维度的权重分配。

### 主维度权重配置

```python
# 各维度权重配置（总和应为1.0）
WEIGHT_CONFIG = {
    'fundamental': 0.40,      # 基本面权重
    'volume': 0.30,           # 成交量权重
    'price': 0.30,            # 成交价格权重
}
```

**说明**：
- 所有权重总和应为1.0（或100%）
- 各维度权重可以自由调整，但建议保持总和为1.0
- 如果某个维度的数据完全不可用，程序会自动将该维度权重设为0，并重新归一化其他权重

### 基本面子维度权重

```python
# 基本面子维度权重配置（总和应为1.0）
FUNDAMENTAL_WEIGHTS = {
    'pe_ratio': 0.20,         # 市盈率权重
    'pb_ratio': 0.20,         # 市净率权重
    'roe': 0.25,              # 净资产收益率权重
    'revenue_growth': 0.20,   # 营收增长率权重
    'profit_growth': 0.15,    # 利润增长率权重
}
```

**说明**：
- 各子维度权重总和应为1.0
- 详细评分标准请参考 [评分指标文档](scoring.md)

### 成交量子维度权重

```python
# 成交量子维度权重配置（总和应为1.0）
VOLUME_WEIGHTS = {
    'volume_ratio': 0.40,     # 量比权重
    'turnover_rate': 0.30,    # 换手率权重
    'volume_trend': 0.30,     # 成交量趋势权重
}
```

### 价格子维度权重

```python
# 价格子维度权重配置（总和应为1.0）
PRICE_WEIGHTS = {
    'price_trend': 0.35,      # 价格趋势权重
    'price_position': 0.30,   # 价格位置权重
    'volatility': 0.35,        # 波动率权重
}
```

### 评分范围配置

```python
# 评分范围
SCORE_MIN = 0
SCORE_MAX = 100
```

---

## 命令行参数

程序支持丰富的命令行参数，可以通过 `python stock_selector.py --help` 查看完整帮助信息。

### 基础参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--refresh` | flag | False | 强制刷新缓存，忽略所有缓存数据，重新从API获取 |
| `--strategy` | str | `multi_factor` | 选股策略（目前仅支持 `multi_factor`） |
| `--factor-set` | str | `fundamental` | 因子组合 (`fundamental`: 基本面+成交量+价格因子, `index_weight`: 指数权重变化趋势因子) |
| `--top-n` | int | 10 | 返回前N只股票（从config.TOP_N读取默认值） |
| `--stocks` | list | None | 指定股票代码列表（如：`--stocks 000001 000002`） |
| `--board` | list | `['main']` | 板块类型，可多选（如：`--board main gem`）<br/>可选值：`main`(主板), `sme`(中小板), `gem`(创业板), `star`(科创板), `bse`(北交所), `b`(B股) |
| `--workers` | int | 10 | 线程数（从config.DEFAULT_MAX_WORKERS读取默认值） |
| `--cache-info` | str | None | 查看指定股票的缓存数据详情 |

### 指数权重因子组合专用参数

当 `--factor-set index_weight` 时，可使用以下参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--indices` | list | None | 指定要追踪的指数代码列表（如：`000300.SH 000905.SH`）<br/>如果不指定，使用config.INDEX_WEIGHT_CONFIG中的配置 |
| `--lookback-days` | int | 60 | 回看天数（用于计算权重趋势）<br/>如果不指定，使用config.INDEX_WEIGHT_CONFIG中的配置 |

### 通知参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--notify` | flag | False | 启用通知功能（邮件/企业微信）<br/>收件人从config.py的EMAIL_CONFIG或WECHAT_CONFIG读取 |
| `--notify-throttle` | flag | False | 启用通知防骚扰模式：仅在交易日15:00之后发送，且每个邮箱每天最多发送一次 |

### 使用示例

```bash
# 选择主板前10只股票（使用fundamental因子组合）
python stock_selector.py --board main --top-n 10

# 评估指定股票
python stock_selector.py --stocks 000001 000002 600000

# 选择主板和创业板股票
python stock_selector.py --board main gem --top-n 30

# 强制刷新缓存
python stock_selector.py --refresh --board main

# 使用指数权重因子组合
python stock_selector.py --factor-set index_weight --top-n 20

# 指定指数和回看天数
python stock_selector.py --factor-set index_weight --indices 000300.SH 000905.SH --lookback-days 90

# 启用通知功能
python stock_selector.py --board main --top-n 10 --notify

# 启用通知防骚扰模式
python stock_selector.py --board main --top-n 10 --notify --notify-throttle

# 查看指定股票的缓存数据详情
python stock_selector.py --cache-info 000001
```

---

## 板块类型配置

### 支持的板块类型

```python
# 板块类型配置
BOARD_TYPES = {
    'main': '主板',      # 主板
    'sme': '中小板',     # 中小板
    'gem': '创业板',     # 创业板
    'star': '科创板',    # 科创板
    'bse': '北交所',     # 北交所
    'b': 'B股',          # B股
}
```

### 默认板块筛选

```python
# 默认板块筛选（只选主板）
DEFAULT_BOARD_TYPES = ['main']  # 可以修改为 ['main', 'gem'] 等
```

**说明**：
- 默认只选择主板股票
- 可以通过命令行参数 `--board` 覆盖默认设置
- 可以同时选择多个板块类型（如：`--board main gem`）

---

## 数据获取参数

```python
# 数据获取参数
LOOKBACK_DAYS = 60  # 回看天数（用于获取K线数据）

# K线数据缓存配置
KLINE_CACHE_RETENTION_DAYS = 250  # K线数据保留天数（约1年，250个交易日）
```

**说明**：
- `LOOKBACK_DAYS`：获取K线数据时回看的天数，默认60天
- `KLINE_CACHE_RETENTION_DAYS`：K线数据在缓存中的保留天数，超过此天数的数据会自动清理
- 更多缓存机制说明请参考 [缓存机制文档](cache.md)

---

## 通知配置

通知配置位于 `config.py` 文件中的 `EMAIL_CONFIG` 和 `WECHAT_CONFIG`。

### 邮件通知配置

```python
EMAIL_CONFIG = {
    'enabled': False,  # 是否启用邮件通知（运行时通过--notify参数启用）
    'default_recipients': ['posterhan@126.com'],  # 默认收件人列表
    'tencent_cloud': {
        'secret_id': None,   # 腾讯云SecretId（可从环境变量TENCENT_SECRET_ID获取）
        'secret_key': None,  # 腾讯云SecretKey（可从环境变量TENCENT_SECRET_KEY获取）
        'region': 'ap-guangzhou',  # 地域
        'from_email': None,  # 发件人邮箱（可从环境变量TENCENT_FROM_EMAIL获取）
        'from_name': 'A股选股程序',  # 发件人名称
    }
}
```

**说明**：
- 详细的邮件配置方法请参考 [环境配置文档](setup.md#腾讯云邮件推送配置)
- 环境变量配置优先于配置文件配置

### 企业微信通知配置

```python
WECHAT_CONFIG = {
    'enabled': False,  # 是否启用企业微信通知（运行时通过--notify参数启用）
    'webhook_url': None,  # 企业微信机器人Webhook URL（可从环境变量WECHAT_WEBHOOK_URL获取）
}
```

**说明**：
- 详细的企业微信配置方法请参考 [环境配置文档](setup.md#企业微信通知配置)
- 环境变量配置优先于配置文件配置

---

## 指数权重策略配置

指数权重策略的配置位于 `config.py` 文件中的 `INDEX_WEIGHT_CONFIG`。

```python
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
}
```

**说明**：
- `tracked_indices`：要追踪的指数代码列表
- `lookback_days`：计算权重趋势时回看的天数
- `score_weights`：各评分维度的权重（总和应为1.0）
- `multi_index_bonus`：如果股票在多个指数中都有权重上升趋势，给予的加分系数
- 详细的指数权重策略说明请参考 `docs/index_weight_strategy_technical_plan.md`

---

## 多线程配置

```python
# 多线程配置
DEFAULT_MAX_WORKERS = 10  # 默认线程数
```

**说明**：
- 可以通过命令行参数 `--workers` 覆盖默认值
- 建议根据网络环境和API调用频率限制调整线程数
- 注意Tushare的调用频率限制，避免触发限流

---

## 配置修改说明

1. **权重配置**：修改 `config.py` 中的权重配置后，重启程序生效
2. **环境变量配置**：环境变量配置优先于配置文件配置
3. **命令行参数**：命令行参数优先级最高，可以覆盖配置文件中的默认值
4. **配置文件位置**：所有配置都在项目根目录的 `config.py` 文件中

## 相关文档

- [环境配置文档](setup.md) - 环境变量配置方法
- [评分指标文档](scoring.md) - 评分维度和计算公式
- [缓存机制文档](cache.md) - 缓存策略和配置

