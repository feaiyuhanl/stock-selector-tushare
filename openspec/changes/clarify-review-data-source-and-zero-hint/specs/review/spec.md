## ADDED Requirements

### Requirement: 复盘数据来源与零条预期

复盘 SHALL 仅处理**过去 N 个交易日**（不含当日），且仅当 `strategy_recommendations` 中**已有**该日期的推荐时，才对「有推荐且无复盘」的条目写入 `review_summary`。「自动补齐」只对 `(trade_date, strategy_name, stock_code)` 在 `strategy_recommendations` 中存在且 `check_review_exists` 为 False 的条目补写；**不会**为过去从未跑过选股的日子生成推荐。若过去 N 日从未运行选股或 `strategy_recommendations` 无对应日期记录，则自动复盘「处理日期数: 0/N」「新增: 0 条」「更新: 0 条」、`review_summary` 为空、飞书同步「各策略均无复盘数据」为**预期**。首次或新环境需**连续多日运行选股**，在 `strategy_recommendations` 中积累数据后，复盘与飞书才会有结果。

#### Scenario: 复盘仅基于已有推荐

- **WHEN** 执行前 N 日复盘，对某 `trade_date` 调用 `get_recommendations(trade_date)`
- **THEN** 仅当 `strategy_recommendations` 中存在该日期的推荐时，才对有推荐且 `check_review_exists` 为 False 的条目写入 `review_summary`；若该日期从未跑过选股则无推荐、不写入

#### Scenario: 零条为预期

- **WHEN** 过去 N 个交易日均未运行过选股，或 `strategy_recommendations` 中无对应日期的记录
- **THEN** 自动复盘输出「处理日期数: 0/N」「新增: 0 条」「更新: 0 条」为**预期**；`review_summary` 为空、飞书同步「各策略均无复盘数据」亦为预期
