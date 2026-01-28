## ADDED Requirements

### Requirement: 当日或最近交易日的推荐写入复盘占位

当 `get_analysis_date()` 对应的日期（当日或非交易日时的最近交易日）在 `strategy_recommendations` 中有推荐时，系统 SHALL 在 `auto_review_last_n_days` 中对该日写入**占位复盘**：`recommendation_date`、`strategy_name`、`strategy_type`、`stock_code`、`stock_name`、`recommendation_price`、`rank` 来自推荐；`day1_price`–`day10_price`、`day1_score`–`day10_score`、`average_score`、`total_score` 为 `NULL`，`valid_days=0`。若该 `(recommendation_date, strategy_name, stock_code)` 已存在则跳过。便于飞书同步至少获得「待跟踪、最新价打分为空」的一行。

#### Scenario: 当日有推荐时写入占位

- **WHEN** `auto_review_last_n_days` 执行，且 `get_analysis_date()` 对应的 `trade_date` 在 `strategy_recommendations` 中有推荐
- **THEN** 对每条有推荐且 `check_review_exists(trade_date, strategy_name, stock_code)` 为 False 的条目，调用 `save_review_summary` 写入占位：`daily_prices`、`daily_scores` 为空或等价，`day1`–`day10`、`average_score`、`total_score` 为 `NULL`，`valid_days=0`
