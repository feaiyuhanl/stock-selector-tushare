# 复盘功能说明

## 概述

复盘功能用于评估策略推荐结果的实际表现，通过跟踪推荐股票在后续交易日中的价格变化，计算表现评分，帮助验证和优化选股策略。

## 功能特性

### 1. 自动保存推荐结果

每次执行选股后，系统会自动将推荐结果保存到数据库表 `strategy_recommendations` 中，包含：
- 推荐日期
- 策略名称和类型
- 股票代码和名称
- 排名和评分
- 策略特定的指标（以JSON格式存储）

### 2. 自动复盘

每次选股完成后，系统会自动复盘**前 N 个交易日**（默认 10 个，不含当日）的推荐结果，计算每只股票的表现评分，并保存到 `review_summary` 表中。**复盘范围不包含当日**（当日无后续交易日数据，仅做推荐保存）。

### 3. 每次运行自动更新当日推荐与前 N 日复盘

- **当日最新推荐**：每次运行任何策略后，自动更新并记录当日（`get_analysis_date()`）的选股结果到 `strategy_recommendations`；若当日该策略已有推荐则覆盖。
- **前 N 日复盘**：每次运行任何策略后，自动对前 N 个交易日执行复盘；**已有复盘结果的 (日期, 策略, 股票) 会跳过，不重复复盘**。

### 4. 复盘由 config 控制，无 CLI 参数

复盘为**自动**：选股后自动复盘最近 10 个交易日（`AUTO_REVIEW_CONFIG.review_days`）内所有推荐结果，并自动查缺补漏。复盘天数、起始日期、是否自动复盘、是否自动补齐等均通过 `config.AUTO_REVIEW_CONFIG` 配置。

**已移除的 CLI 参数**：`--review`、`--review-date`、`--review-days`、`--fill-review-gaps`、`--no-auto-review` 已全部移除。

### 5. 自动补齐

- **本地复盘**：前 N 日复盘循环中，仅对「有推荐且无复盘」的条目写入，等价于自动补齐缺失；无单独命令。**前提**：复盘只处理 `strategy_recommendations` 中**已有**该日期推荐的条目；**不会**为过去从未跑过选股的日子生成推荐。若过去 N 日从未运行选股，则处理 0 条、飞书无数据属**预期**；首次或新环境需**连续多日运行选股**，在 `strategy_recommendations` 中积累数据后，复盘与飞书才会有结果。
- **飞书表格**：同步时若表格不存在则创建，存在则全量写入，等价于自动补齐表格缺失。

### 6. 飞书电子表格同步

由 **config** `FEISHU_SHEETS_CONFIG.enabled` 控制；为 True 且配置好 `folder_token`、`app_id`、`app_secret` 时，复盘流程结束后自动将各策略的复盘结果同步到飞书电子表格：

- **一个策略一个表格**，命名：`YYYY_策略_复盘结果`（如 `2026_ScoringStrategy_复盘结果`）
- 表格列与 `review_summary` / 策略复盘内容一致；表格不存在时自动创建（使用飞书 Sheets API `POST /open-apis/sheets/v3/spreadsheets`），再通过 values 接口写入
- 同步失败不阻塞选股/复盘/通知，仅打日志
- 环境变量可覆盖：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_FOLDER_TOKEN`
- 飞书应用需具备权限：`drive:drive`（云文档）、`sheets:spreadsheet`（电子表格）、创建电子表格；`folder_token` 为目标文件夹 token（不要求以 `fld` 开头），可从飞书云文档对应文件夹的 URL 或 API 获取

---

## 评分规则

复盘评分基于累计涨幅计算：

- **基准价格**：推荐当天的收盘价
- **计算公式**：
  ```
  累计涨幅 = (当前收盘价 - 推荐当天收盘价) / 推荐当天收盘价
  
  打分规则：
  - 如果累计涨幅 = 0: 60分
  - 如果累计涨幅 > 0: 60 + min(40, 累计涨幅 * 100)  （最高100分）
  - 如果累计涨幅 < 0: 60 + max(-60, 累计涨幅 * 100)  （最低0分）
  ```

**示例：**
- 涨幅 10% => 60 + 10 = 70分
- 涨幅 -5% => 60 - 5 = 55分
- 涨幅 50% => 60 + 40 = 100分（封顶）
- 涨幅 -70% => 60 - 60 = 0分（封底）

---

## 数据库表结构

### strategy_recommendations 表

保存策略推荐结果：

| 字段 | 类型 | 说明 |
|------|------|------|
| trade_date | TEXT | 推荐日期（YYYYMMDD） |
| strategy_name | TEXT | 策略名称 |
| strategy_type | TEXT | 策略类型 |
| stock_code | TEXT | 股票代码 |
| stock_name | TEXT | 股票名称 |
| rank | INTEGER | 排名 |
| score | REAL | 综合得分 |
| metrics_json | TEXT | 策略特定指标（JSON格式） |
| category | TEXT | 分类标记 |

### review_summary 表

保存复盘汇总记录：

| 字段 | 类型 | 说明 |
|------|------|------|
| recommendation_date | TEXT | 推荐日期（YYYYMMDD） |
| strategy_name | TEXT | 策略名称 |
| strategy_type | TEXT | 策略类型 |
| stock_code | TEXT | 股票代码 |
| stock_name | TEXT | 股票名称 |
| recommendation_price | REAL | 推荐当天的收盘价 |
| rank | INTEGER | 推荐时的排名 |
| day1_price ~ day10_price | REAL | 第1-10个交易日的收盘价 |
| day1_score ~ day10_score | REAL | 第1-10个交易日的评分 |
| average_score | REAL | 平均分（10个交易日的平均） |
| total_score | REAL | 总评分（第10个交易日的评分） |
| valid_days | INTEGER | 有效交易日数 |

---

## 命令行使用

### 正常选股（自动保存、自动复盘、飞书同步均由 config 控制）

```bash
# 执行选股；自动复盘、飞书同步、复盘天数、起始日期、补齐均由 config 控制，无 CLI 参数
python stock_selector.py --factor-set fundamental --top-n 10
```

### 仅同步飞书（临时测试）`--sync-feishu-only`

将本地复盘结果（`review_summary`）按策略同步到飞书电子表格。**若 `ScoringStrategy` 与 `IndexWeightStrategy` 均无复盘数据，会先自动执行 combined 选股与复盘，再同步**；若任一侧已有数据则仅同步，不执行选股与复盘。此模式下不检查 `FEISHU_SHEETS_CONFIG.enabled`，但仍需 `folder_token`、`app_id`、`app_secret` 已配置（config 或环境变量），否则报错退出。

```bash
python stock_selector.py --sync-feishu-only
```

---

## 配置说明

复盘、飞书同步、复盘天数、起始日期、自动补齐**均由 config 控制，无 CLI 覆盖**：

```python
AUTO_REVIEW_CONFIG = {
    'enabled': True,              # 是否启用自动复盘
    'review_days': 10,            # 复盘天数（交易日数）
    'review_start_date': None,     # 复盘起始日期 YYYYMMDD，只处理该日期及以后；None 不限制
    'auto_update': True,          # 自动补齐（前 N 日循环中只写缺失条）
}
```

### 飞书电子表格同步

```python
# 环境变量可覆盖：FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_FOLDER_TOKEN
FEISHU_SHEETS_CONFIG = {
    'enabled': True,              # 是否同步复盘结果到飞书（默认 True，与「复盘后自动同步」一致；置 False 可关闭）
    'folder_token': None,         # 目标文件夹 token
    'app_id': None,
    'app_secret': None,
}
```

- **权限**：飞书应用需开通 `drive:drive`、`sheets:spreadsheet`、创建电子表格；文件夹需在应用可访问范围内
- **folder_token**：在飞书云文档中进入目标文件夹，从 URL 或「获取链接」等处获取；格式不要求以 `fld` 开头

---

## 使用示例

### 示例1：选股后自动复盘

```bash
# 选股完成后自动复盘最近 10 个交易日的推荐结果，并自动查缺补漏
python stock_selector.py --factor-set fundamental --top-n 10
```

### 示例2：查询数据库中的复盘数据

```python
from data.cache_manager import CacheManager
from autoreview import ReviewCache

cache_manager = CacheManager()
review_cache = ReviewCache(cache_manager)

# 查询某日所有策略的复盘汇总
review_data = review_cache.get_review_summary(recommendation_date='20240115')

# 查询某策略的复盘统计（按总评分排序）
review_data = review_cache.get_review_summary(
    recommendation_date='20240115',
    strategy_name='ScoringStrategy'
)

# 查询某股票的历史复盘表现
review_data = review_cache.get_review_summary(stock_code='000001')
```

---

## 注意事项

1. **数据完整性**：确保复盘日期已执行过选股，且有K线数据
2. **交易日处理**：复盘天数按实际交易日计算（排除非交易日）
3. **价格缺失处理**：如果某日无收盘价数据，该日评分显示为NULL，不计入平均分
4. **性能考虑**：复盘需要查询多个表，对大批量股票可能需要一定时间
5. **数据更新**：前 N 日复盘会自动补齐缺失（只写无复盘记录的条目）；飞书同步时会创建缺失表格并写入
6. **缓存路径**：飞书同步与选股、复盘使用同一 `config.CACHE_DIR` 下的 `stock_cache.db`（绝对路径，与运行目录无关）。若遇「无复盘数据」可核对程序输出的「使用的 DB」是否与本地查看的 SQLite 文件一致；并检查 `review_summary` 中的 `strategy_name` 是否为 `ScoringStrategy`、`IndexWeightStrategy`。

---

## 常见问题

### Q: 为什么某些日期的复盘数据缺失？

A: 可能的原因：
- 该日期未执行选股
- 该日期的K线数据尚未获取
- 该日期早于 `AUTO_REVIEW_CONFIG.review_start_date`（若已配置）
- 前 N 日复盘会自动补齐缺失，只需再次运行选股触发复盘

### Q: 为什么自动复盘显示「处理日期数: 0/10」「新增: 0 条」，飞书同步「各策略均无复盘数据」？

A: 复盘仅处理 `strategy_recommendations` 中**已有**该日期推荐的条目；不会为过去从未跑选股的日子生成推荐。若过去 N 个交易日均未运行选股，则 0 条、无复盘数据属**预期**。解决：**连续多日运行选股**（如每天运行 `python stock_selector.py --factor-set combined`），在 `strategy_recommendations` 中积累各日推荐后，复盘与飞书同步才会有结果。若本地 SQLite 确有复盘数据却仍提示无数据：可查看程序输出的「[飞书同步] 使用的 DB」是否与本地打开的 `stock_cache.db` 一致（现已改为 `config.CACHE_DIR` 绝对路径）；以及「诊断: review_summary 中的 strategy_name 有:」是否包含 `ScoringStrategy`、`IndexWeightStrategy`，若为其它名称则需与飞书同步所用策略名一致。

### Q: 如何查看历史复盘表现？

A: 可以通过数据库查询 `review_summary` 表，或使用 `ReviewCache` 类的方法查询。

### Q: 自动复盘会影响程序运行速度吗？

A: 自动复盘在选股完成后执行，会额外花费一些时间。若不需要，在 config 中设置 `AUTO_REVIEW_CONFIG.enabled: False`。

---

## 相关文档

- [缓存机制说明](cache.md)
- [策略说明](../README.md#策略说明)

