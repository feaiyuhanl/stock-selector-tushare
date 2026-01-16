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

每次选股完成后，系统会自动复盘前N个交易日（默认10个交易日）的推荐结果，计算每只股票的表现评分，并保存到 `review_summary` 表中。

### 3. 手动复盘

可以通过命令行参数手动复盘指定日期的推荐结果。

### 4. 补齐缺失数据

支持自动补齐之前交易日缺失的复盘数据。

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

### 正常选股（自动保存和自动复盘）

```bash
# 执行选股，会自动保存推荐结果并自动复盘前10个交易日
python stock_selector.py --factor-set fundamental --top-n 10
```

### 手动复盘

```bash
# 复盘指定日期的推荐结果
python stock_selector.py --review --review-date 20240115 --review-days 10

# 只复盘特定策略的结果
python stock_selector.py --review --review-date 20240115 --review-days 10 --strategy ScoringStrategy
```

### 补齐缺失数据

```bash
# 补齐之前交易日缺失的复盘数据（不执行选股）
python stock_selector.py --fill-review-gaps
```

### 禁用自动复盘

```bash
# 执行选股但不自动复盘
python stock_selector.py --factor-set fundamental --no-auto-review
```

---

## 配置说明

在 `config.py` 中可以配置自动复盘行为：

```python
AUTO_REVIEW_CONFIG = {
    'enabled': True,              # 是否启用自动复盘
    'review_days': 10,            # 复盘天数（默认10个交易日）
    'auto_update': True,          # 是否自动补齐缺失数据
}
```

---

## 使用示例

### 示例1：查看某日的复盘报告

```bash
python stock_selector.py --review --review-date 20240115 --review-days 10
```

输出示例：
```
【复盘报告】
推荐日期: 20240115
复盘天数: 10个交易日
================================================================================
排名    | 代码      | 名称      | 推荐价    | 第1日     | 第2日     | ... | 平均分    | 总评分
--------------------------------------------------------------------------------
1       | 000001    | 平安银行  | 10.50     | 60.5      | 62.3      | ... | 68.5      | 75.2
2       | 000002    | 万科A     | 8.30      | 58.2      | 59.1      | ... | 66.2      | 71.8
...

【统计信息】
  总股票数: 10
  平均总评分: 65.8
  最高评分: 75.2 (000001)
  最低评分: 55.1 (000002)
================================================================================
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
5. **数据更新**：如果K线数据后补录，可以运行 `--fill-review-gaps` 补齐复盘记录

---

## 常见问题

### Q: 为什么某些日期的复盘数据缺失？

A: 可能的原因：
- 该日期未执行选股
- 该日期的K线数据尚未获取
- 可以运行 `--fill-review-gaps` 补齐缺失数据

### Q: 如何查看历史复盘表现？

A: 可以通过数据库查询 `review_summary` 表，或使用 `ReviewCache` 类的方法查询。

### Q: 自动复盘会影响程序运行速度吗？

A: 自动复盘在选股完成后异步执行，会额外花费一些时间。如果不需要可以禁用：`--no-auto-review` 或在配置中设置 `enabled: False`。

---

## 相关文档

- [缓存机制说明](cache.md)
- [策略说明](../README.md#策略说明)

