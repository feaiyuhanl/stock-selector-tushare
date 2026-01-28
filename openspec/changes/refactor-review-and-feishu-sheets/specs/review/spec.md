## ADDED Requirements

### Requirement: 每次策略运行后自动更新前几个交易日的复盘

每次运行任何选股策略后，系统 SHALL 自动对**前 N 个交易日**（`AUTO_REVIEW_CONFIG.review_days`，如 10）执行复盘，计算并写入 `review_summary`；复盘范围不包含“当日”（当日无后续交易日数据，仅做推荐保存）。

#### Scenario: 单策略运行后触发前 N 日复盘

- **WHEN** 用户执行 `stock_selector.py` 选股（如 `--factor-set fundamental`）且未使用 `--no-auto-review`
- **THEN** 选股与 `_save_recommendations` 完成后，系统对前 N 个交易日（不含当日）调用 `auto_review_last_n_days(days=N)`，对存在 `strategy_recommendations` 的 `(trade_date, strategy_name, stock_code)` 执行复盘逻辑并写入 `review_summary`

#### Scenario: combined 模式下两策略均保存推荐后触发一次前 N 日复盘

- **WHEN** 用户执行 `--factor-set combined`，两个策略均完成选股并各自 `_save_recommendations`
- **THEN** 在两次保存推荐之后、通知之前，调用一次 `auto_review_last_n_days`，其内部按 `strategy_recommendations` 中的 `strategy_name` 分组，对前 N 个交易日分别处理 ScoringStrategy、IndexWeightStrategy 等所有出现过的策略的推荐记录

#### Scenario: 前 N 个交易日不包含当日

- **WHEN** 计算“前 N 个交易日”列表
- **THEN** 系统使用 `_get_trading_dates_before`，end_date 为“当前分析日”或“昨日”的语义，得到的列表不包含 `get_analysis_date()` 的当日，从而当日只参与推荐写入，不参与复盘计算

---

### Requirement: 每次策略运行后自动更新并记录当日最新推荐结果

每次运行任何选股策略后，系统 SHALL 将当日（`get_analysis_date()` 的 `trade_date`）的选股结果写入 `strategy_recommendations`；若当日该策略已有推荐记录，则按现有逻辑覆盖，从而“自动更新记录当日最新推荐结果”。

#### Scenario: 选股完成后保存当日推荐

- **WHEN** 选股完成并得到 `results` DataFrame
- **THEN** 系统调用 `_save_recommendations(selector, strategy, results)`，使用 `get_analysis_date().strftime('%Y%m%d')` 作为 `trade_date`，将 `strategy_name`、`strategy_type` 及 results 中的 `code`、`name`、`score`、`rank` 等写入 `strategy_recommendations`；若该 `(trade_date, strategy_name)` 已有记录，则先删除再插入（与现有 `RecommendationCache.save_recommendations` 行为一致）

#### Scenario: combined 模式下两策略分别保存当日推荐

- **WHEN** `--factor-set combined` 下两个策略分别完成选股
- **THEN** 每个策略在 `_execute_selection` 与 `print_results` 之后、复盘之前，各调用一次 `_save_recommendations`，从而两策略的当日推荐均被记录到 `strategy_recommendations`

---

### Requirement: 已有复盘结果则跳过不重复复盘

对任意 `(recommendation_date, strategy_name, stock_code)`，若 `review_summary` 中已存在该条复盘记录，系统 SHALL 跳过该条，不重新计算、不覆盖，即“复盘完成或是有结果，无需重复复盘”。

#### Scenario: 单条已有记录则跳过

- **WHEN** `review_single_date` 或 `auto_review_last_n_days` 处理到某条 `(trade_date, strategy_name, stock_code)`
- **THEN** 先调用 `review_cache.check_review_exists(trade_date, strategy_name, stock_code)`；若返回 True，则不调用 `save_review_summary`，不请求 K 线、不计算 `daily_scores`，该条跳过；仅当返回 False 时执行复盘计算并保存

#### Scenario: 部分有新、部分已有时仅处理新条

- **WHEN** 某 `trade_date` 下某策略有 10 条推荐，其中 3 条已在 `review_summary`，7 条不存在
- **THEN** 系统对 3 条跳过，对 7 条执行复盘并 `save_review_summary`；汇总统计中“更新”计数不包含被跳过的 3 条，“新增”仅针对 7 条
