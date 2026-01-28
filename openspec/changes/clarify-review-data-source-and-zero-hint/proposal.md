# Change: 澄清复盘数据来源与零条预期，增加自动复盘与飞书同步的提示

## Why

用户首次运行或新环境中，每次选股后自动复盘输出「处理日期数: 0/10」「新增记录: 0 条」「更新记录: 0 条」，飞书同步为「各策略均无复盘数据」。提案中的「自动补齐」仅对 `strategy_recommendations` **已有**该日推荐且无复盘记录的条目补写，**不会**为过去从未跑过选股的日子生成推荐。若过去 N 个交易日均未执行过选股，则 0 条、无复盘数据属**预期**。当前缺少说明，易被误认为 bug；需在规范、文档和运行时提示中澄清。

## What Changes

- **MODIFIED** review 规范：**ADDED** Requirement「复盘数据来源与零条预期」，明确复盘仅处理 `strategy_recommendations` 中已有推荐的日期；「自动补齐」只补「有推荐且无复盘」的条目；过去 N 日无历史推荐时 0 条与飞书无数据为预期；首次或新环境需**连续多日运行选股**积累数据后才有复盘与飞书结果。
- **MODIFIED** `autoreview/auto_review.py`：当 `auto_review_last_n_days` 输出「处理日期数: 0/N」且 `total_new + total_updated == 0` 时，在【自动复盘完成】后增加一行提示：过去 N 个交易日无历史推荐数据，本次无可复盘内容；请连续多日运行选股以在 `strategy_recommendations` 中积累数据，后续复盘与飞书同步才会有结果。
- **MODIFIED** `docs/review.md`：在「自动补齐」与「常见问题」等处补充：复盘与飞书有数据的前提是过去 N 日运行过选股且在 `strategy_recommendations` 有对应日期的推荐；首次或新环境需连续多日运行选股。
- **MODIFIED** `stock_selector._run_feishu_sync`（可选）：在输出「[飞书同步] 同步完成，各策略均无复盘数据。」时，追加一句短提示：原因多为过去 N 日未运行选股，可参见 `docs/review.md` 或连续多日运行选股后重试。

## Impact

- **Affected specs**：`review`（ADDED Requirement）
- **Affected code**：
  - `autoreview/auto_review.py`：`auto_review_last_n_days` 在 0 条且 0 新增/更新时增加提示
  - `docs/review.md`：补充数据来源、零条预期与连续多日运行说明
  - `stock_selector.py`：`_run_feishu_sync` 在「各策略均无复盘数据」时增加可选短提示
