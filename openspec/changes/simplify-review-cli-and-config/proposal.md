# Change: 简化复盘与飞书相关 CLI，改由 config 统一控制

## Why

复盘与飞书同步的 CLI 参数（`--no-auto-review`、`--fill-review-gaps`、`--review-days`）分散且需手动指定，增加使用成本。希望改为：复盘与飞书均由 config 开关控制、自动执行；复盘天数与起始日期在 config 配置；复盘与飞书表格自动补齐缺失；CLI 仅保留 `--review` / `--review-date` 用于按需查看指定日期的复盘报告。

## What Changes

- **MODIFIED**: 自动复盘由 `AUTO_REVIEW_CONFIG.enabled` 控制，选股完成后若为 True 则自动跑前 N 日复盘，**移除** `--no-auto-review`。
- **MODIFIED**: 飞书同步由 `FEISHU_SHEETS_CONFIG.enabled` 控制，复盘结束后若为 True 则自动同步，无需 CLI 指定；**无新增/移除飞书相关 CLI**。
- **MODIFIED**: 复盘天数仅来自 `AUTO_REVIEW_CONFIG.review_days`（默认 10），**移除** `--review-days`；手动 `--review --review-date` 时也从此配置读取天数。
- **MODIFIED**: 复盘自动补齐本地缺失：前 N 日复盘循环中只对「有推荐且无复盘」的条目写入，等同自动补齐；**移除** `--fill-review-gaps` 及其处理逻辑；飞书表格自动补齐：同步时不存在则创建、存在则按策略全量写入，已满足「补齐表格缺失」。
- **ADDED**: `AUTO_REVIEW_CONFIG.review_start_date`（如 `"20240101"` 或 `None`）：复盘只处理该日期及以后的交易日；有推荐结果的日期才参与复盘更新。
- **REMOVED**: CLI 参数 `--no-auto-review`、`--fill-review-gaps`、`--review-days`；以及 `_handle_fill_review_gaps` 入口。

## Impact

- **Affected specs**: `review`，`feishu-sheets-sync`（轻量，飞书仍由 config 开关控制）
- **Affected code**:
  - `config.py`：`AUTO_REVIEW_CONFIG` 新增 `review_start_date`；`review_days`、`enabled` 已有；`FEISHU_SHEETS_CONFIG.enabled` 已有
  - `stock_selector.py`：移除 `--no-auto-review`、`--fill-review-gaps`、`--review-days`；移除 `_handle_fill_review_gaps` 及对应的 `args.fill_review_gaps` 分支；主流程中复盘条件改为仅 `config.AUTO_REVIEW_CONFIG.get('enabled', True)`；`_handle_review_command` 的 `days` 改为从 `config.AUTO_REVIEW_CONFIG.get('review_days', 10)` 读取
  - `autoreview/auto_review.py`：`auto_review_last_n_days` 在得到 `trading_dates` 后，若 `review_start_date` 非空则过滤为 `>= review_start_date`；可移除或保留 `fill_missing_reviews`（不再被调用则保留也无妨，为减负可删）
