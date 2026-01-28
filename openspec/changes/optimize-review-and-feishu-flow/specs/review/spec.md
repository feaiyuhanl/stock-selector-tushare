## MODIFIED Requirements

### Requirement: 复盘相关 CLI 仅保留按需查看，其余由 config 配置

复盘相关命令行参数 SHALL 仅保留 `--review`、`--review-date`，用于按需查看指定日期的复盘报告。**移除** `--review-days`、`--fill-review-gaps`、`--no-auto-review`。复盘天数、起始日期、是否自动复盘、是否自动补齐等 SHALL 全部通过 `config.AUTO_REVIEW_CONFIG`（如 `review_days` 默认 10、`review_start_date`、`enabled`、`auto_update`）配置；手动 `--review --review-date` 时的复盘天数从 `config.AUTO_REVIEW_CONFIG.get('review_days', 10)` 读取。

#### Scenario: 复盘天数从 config 读取

- **WHEN** 执行自动复盘或 `--review --review-date` 的复盘
- **THEN** `days` 使用 `config.AUTO_REVIEW_CONFIG.get('review_days', 10)`，不由 CLI 传入；不存在 `--review-days` 参数

#### Scenario: 禁用自动复盘与补齐由 config 控制

- **WHEN** 用户希望禁用选股后自动复盘或不再使用补齐
- **THEN** 通过修改 `config.AUTO_REVIEW_CONFIG.enabled` 或相关配置实现；不存在 `--no-auto-review`、`--fill-review-gaps` 等 CLI

---

### Requirement: 每次选股后自动复盘、复盘完成后自动同步飞书

每次运行选股并保存推荐后，当 `AUTO_REVIEW_CONFIG.enabled` 为 True 时，系统 SHALL 自动对前 N 个交易日（`AUTO_REVIEW_CONFIG.review_days`，默认 10）且符合 `review_start_date` 的日期执行复盘；复盘完成后，当 `FEISHU_SHEETS_CONFIG.enabled` 为 True 且 `folder_token` 等已配置时，系统 SHALL 自动按策略调用飞书同步，将复盘结果写入飞书电子表格。选股、复盘、飞书同步的流程顺序固定，仅由 config 开关控制，无额外 CLI。

#### Scenario: 选股后自动复盘再飞书

- **WHEN** `AUTO_REVIEW_CONFIG.enabled` 为 True，选股并保存推荐完成后
- **THEN** 系统自动调用 `auto_review_last_n_days`；复盘结束后，若 `FEISHU_SHEETS_CONFIG.enabled` 为 True，自动调用 `_run_feishu_sync` 按策略同步到飞书

#### Scenario: 飞书未启用则不同步

- **WHEN** `FEISHU_SHEETS_CONFIG.enabled` 为 False 或 `folder_token` 未配置
- **THEN** 复盘照常执行，飞书同步被跳过，不报错
