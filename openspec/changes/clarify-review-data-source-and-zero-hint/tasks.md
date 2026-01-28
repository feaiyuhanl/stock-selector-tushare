## 1. 规范澄清（review spec）

- [x] 1.1 在 `openspec/changes/clarify-review-data-source-and-zero-hint/specs/review/spec.md` 中 **ADDED** Requirement「复盘数据来源与零条预期」：复盘仅处理过去 N 个交易日（不含当日），且仅当 `strategy_recommendations` 中已有该日期的推荐时才写入 `review_summary`；「自动补齐」只对「有推荐且无复盘」的条目补写，不会为过去未跑选股的日子生成推荐；过去 N 日从未跑选股时 0 条、`review_summary` 为空、飞书无数据属预期；首次或新环境需连续多日运行选股以积累数据。含 Scenario「复盘仅基于已有推荐」与「零条为预期」。

## 2. 自动复盘零条提示

- [x] 2.1 在 `autoreview/auto_review.py` 的 `auto_review_last_n_days` 中，当 `processed_dates == 0` 且 `total_new + total_updated == 0` 时，在打印「【自动复盘完成】」及「处理日期数」「新增」「更新」之后，增加一行：`[自动复盘] 过去 N 个交易日无历史推荐数据，本次无可复盘内容。请连续多日运行选股以在 strategy_recommendations 中积累数据，后续复盘与飞书同步才会有结果。`

## 3. 文档澄清

- [x] 3.1 在 `docs/review.md` 的「自动补齐」小节或「注意事项/常见问题」中补充：复盘只处理 `strategy_recommendations` 中**已有**该日期推荐的条目；若过去 N 日从未运行选股，则处理 0 条、飞书无数据属**预期**；首次或新环境需**连续多日运行选股**，在 `strategy_recommendations` 中积累数据后，复盘与飞书才会有结果。可在「常见问题」增加 Q：为什么自动复盘显示处理 0 条、飞书无数据？

## 4. 飞书同步零条提示（可选）

- [x] 4.1 在 `_run_feishu_sync` 中，当 `force and not any_with_data` 且输出「[飞书同步] 同步完成，各策略均无复盘数据。」后，追加一行短提示：`[飞书同步] 多为过去 N 日未运行选股导致，详见 docs/review.md；连续多日运行选股后重试。`

## 5. 校验

- [x] 5.1 运行 `openspec validate clarify-review-data-source-and-zero-hint --strict --no-interactive` 通过。
