## MODIFIED Requirements

### Requirement: 每次策略运行后自动更新前几个交易日的复盘

每次运行任何选股策略后，当 **config** `AUTO_REVIEW_CONFIG.enabled` 为 True 时，系统 SHALL 自动对**前 N 个交易日**（`AUTO_REVIEW_CONFIG.review_days`，默认 10）且 **>= `AUTO_REVIEW_CONFIG.review_start_date`**（若配置）的日期执行复盘，计算并写入 `review_summary`；复盘范围不包含当日。**不存在** `--no-auto-review` 等 CLI 覆盖，仅由 config 控制。

#### Scenario: config 启用时自动复盘

- **WHEN** `AUTO_REVIEW_CONFIG.enabled` 为 True，选股并保存推荐完成后
- **THEN** 系统自动调用 `auto_review_last_n_days`，复盘前 N 日（N 来自 `review_days`），且仅处理日期 >= `review_start_date`（若 `review_start_date` 已配置）

#### Scenario: review_start_date 过滤

- **WHEN** `AUTO_REVIEW_CONFIG.review_start_date` 为 `"20240101"` 等非空值
- **THEN** `auto_review_last_n_days` 得到的 `trading_dates` 仅保留 `d >= review_start_date`，只对对应时间及之后、且有推荐结果的日期更新复盘记录

#### Scenario: 自动补齐复盘缺失

- **WHEN** 执行前 N 日复盘
- **THEN** 对每条 `(trade_date, strategy_name, stock_code)` 若 `check_review_exists` 为 False 则写入，有则跳过；等价于自动补齐本地复盘缺失，无需单独 `--fill-review-gaps` 命令

---

### Requirement: 复盘天数与起始日期由 config 配置

复盘天数 SHALL 来自 `AUTO_REVIEW_CONFIG.review_days`（默认 10）；复盘起始日期 SHALL 来自 `AUTO_REVIEW_CONFIG.review_start_date`（默认 `None`，表示不限制）。**不存在** `--review-days` CLI；手动 `--review --review-date` 时，复盘天数也从 `review_days` 读取。

#### Scenario: 复盘天数从 config 读取

- **WHEN** 执行自动复盘或 `--review --review-date` 的复盘
- **THEN** `days` 使用 `config.AUTO_REVIEW_CONFIG.get('review_days', 10)`，不由 CLI 传入

#### Scenario: 起始日期从 config 读取

- **WHEN** 执行自动复盘
- **THEN** 仅处理 `trading_dates` 中 `>= review_start_date` 的日期；若 `review_start_date` 为空或未配置则不过滤
