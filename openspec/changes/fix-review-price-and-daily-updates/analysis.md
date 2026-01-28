# 复盘功能问题分析与解决方案

## 问题描述

### 问题1：recommendation_price 全部为空
- **现象**：`review_summary` 表中所有记录的 `recommendation_price` 字段都是 `NULL`
- **影响**：无法计算后续交易日的表现评分（因为缺少基准价格）

### 问题2：所有 day1_price, day1_score 等复盘价格都为空
- **现象**：`review_summary` 表中所有记录的 `day1_price`, `day1_score`, `day2_price`, `day2_score` 等字段都是 `NULL`
- **期望行为**：
  - 对于上一个交易日的推荐，本交易日结束应该要更新对应 `day1_price`, `day1_score`
  - 前两个交易日的推荐结果，需要对应更新 `day2_price`, `day2_score`
  - 依次类推

## 问题根因分析

### 根本原因

在 `autoreview/auto_review.py` 的 `auto_review_last_n_days` 方法中，第79行存在以下逻辑：

```python
if self.review_cache.check_review_exists(trade_date, strategy_name, stock_code):
    continue  # 如果记录已存在，直接跳过
```

**问题**：
1. **跳过已存在记录**：一旦记录被创建（即使是占位记录，字段为 `NULL`），后续运行就不会再更新
2. **占位记录无法更新**：
   - 当日推荐时，如果 `recommendation_price` 获取失败（可能因为当日还未收盘），会创建占位记录（`recommendation_price=None`）
   - 历史推荐时，如果 `recommendation_price` 获取失败，也会创建占位记录
   - 这些占位记录后续不会被更新，导致字段永久为空
3. **day1-day10 字段无法增量更新**：
   - 当日推荐时，会创建占位记录（`day1-day10` 都是 `NULL`）
   - 后续交易日，由于 `check_review_exists` 返回 `True`，会跳过更新
   - 即使新的交易日数据可用，也不会更新到已存在的记录中

### 具体场景

1. **场景1：当日推荐时 recommendation_price 为空**
   - 当日推荐时，可能因为：
     - 当日还未收盘，无法获取收盘价
     - K线数据缓存未命中，tushare 拉取失败
   - 创建占位记录：`recommendation_price=None`, `day1-day10=NULL`
   - 后续运行：由于记录已存在，跳过更新
   - **结果**：`recommendation_price` 永久为空

2. **场景2：历史推荐时 day1-day10 无法更新**
   - 历史推荐时，创建记录并计算 `day1-day10`
   - 但如果某些交易日数据不可用，对应的 `dayX` 字段为 `NULL`
   - 后续运行：由于记录已存在，跳过更新
   - **结果**：即使新的交易日数据可用，也不会更新

3. **场景3：当日推荐后续无法更新 day1**
   - 当日推荐时，创建占位记录：`day1-day10=NULL`
   - 下一个交易日：应该更新 `day1_price`, `day1_score`
   - 但由于记录已存在，跳过更新
   - **结果**：`day1` 字段永久为空

## 解决方案

### 核心思路

**不再简单跳过已存在的记录，而是检查并更新缺失的字段**：

1. **对于已存在的记录**：
   - 如果 `recommendation_price` 为空，尝试获取并更新
   - 对于历史推荐，重新计算所有可用的 `day1-day10` 数据
   - 只更新缺失的字段，保留已有的数据

2. **增量更新逻辑**：
   - 检查 `recommendation_price` 是否为空，如果为空则尝试更新
   - 对于历史推荐，重新计算所有可用的交易日数据
   - 如果新的有效天数更多，则更新记录

### 实现细节

#### 1. 添加 `get_existing_review` 方法

在 `autoreview/review_cache.py` 中添加方法，用于获取已存在的记录：

```python
def get_existing_review(self, recommendation_date: str, strategy_name: str, stock_code: str) -> Optional[Dict]:
    """获取已存在的复盘记录"""
    # 返回记录的字典，包含所有字段
```

#### 2. 修改 `auto_review_last_n_days` 方法

在 `autoreview/auto_review.py` 中修改逻辑：

**原逻辑**：
```python
if self.review_cache.check_review_exists(trade_date, strategy_name, stock_code):
    continue  # 跳过已存在记录
```

**新逻辑**：
```python
existing = self.review_cache.get_existing_review(trade_date, strategy_name, stock_code)

if existing is None:
    # 新记录：正常创建
    ...
else:
    # 已存在记录：检查是否需要更新
    # 1. 如果 recommendation_price 为空，尝试更新
    # 2. 对于历史推荐，重新计算所有可用的 day1-day10 数据
    ...
```

#### 3. 更新策略

- **recommendation_price 更新**：
  - 如果现有记录的 `recommendation_price` 为 `None`，尝试获取并更新
  - 如果获取成功，更新记录

- **day1-day10 更新**：
  - 对于历史推荐（非当日），重新计算所有可用的交易日数据
  - 如果新的有效天数更多，则更新记录
  - 如果 `recommendation_price` 被更新，重新计算所有评分

- **当日推荐更新**：
  - 如果 `recommendation_price` 被更新，只更新该字段，保留其他字段

## 修改文件

1. **autoreview/review_cache.py**
   - 添加 `get_existing_review` 方法

2. **autoreview/auto_review.py**
   - 修改 `auto_review_last_n_days` 方法，实现增量更新逻辑

## 测试建议

1. **测试 recommendation_price 更新**：
   - 创建一条 `recommendation_price` 为空的记录
   - 运行复盘，验证是否能更新 `recommendation_price`

2. **测试 day1-day10 更新**：
   - 创建一条 `day1-day10` 为空的记录
   - 运行复盘，验证是否能更新 `day1` 字段

3. **测试增量更新**：
   - 创建一条只有 `day1` 数据的记录
   - 运行复盘，验证是否能更新 `day2` 字段

4. **测试当日推荐更新**：
   - 当日推荐时创建占位记录
   - 下一个交易日运行复盘，验证是否能更新 `day1` 字段

## 预期效果

修复后：
1. **recommendation_price**：如果为空，会在后续运行中尝试更新
2. **day1-day10**：会根据当前日期和推荐日期，自动更新可用的字段
3. **增量更新**：每次运行都会检查并更新缺失的字段，不会跳过已存在的记录
