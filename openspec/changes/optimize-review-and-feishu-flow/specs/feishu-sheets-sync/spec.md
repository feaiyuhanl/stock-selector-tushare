## ADDED Requirements

### Requirement: 临时测试参数仅同步复盘结果到飞书

系统 SHALL 提供临时测试参数 `--sync-feishu-only`：不执行选股、不执行复盘；从本地 `review_summary`（经 `ReviewCache.get_review_summary`）读取已有复盘结果，按策略（如 `ScoringStrategy`、`IndexWeightStrategy`）同步到飞书电子表格。此模式下不检查 `FEISHU_SHEETS_CONFIG.enabled`，以便在 `enabled=False` 时也能测试同步；但仍需 `folder_token`、`app_id`、`app_secret` 等已配置，否则提示错误并退出。

#### Scenario: 仅同步不选股不复盘

- **WHEN** 用户执行 `python stock_selector.py --sync-feishu-only`
- **THEN** 程序不运行选股、不运行 `auto_review_last_n_days`；使用 `CacheManager` 与 `ReviewCache` 从本地 DB 读取 `review_summary`，按策略调用 `sync_review_to_feishu`（或通过 `_run_feishu_sync(..., force=True)`）将结果同步到飞书；完成后直接退出

#### Scenario: 未配置飞书必填项时退出

- **WHEN** `--sync-feishu-only` 且 `folder_token` 或 `app_id`/`app_secret` 未配置
- **THEN** 打印错误提示并 `sys.exit(1)`，不发起同步请求

#### Scenario: force 模式跳过 enabled 检查

- **WHEN** `_run_feishu_sync` 被以 `force=True` 调用（如来自 `--sync-feishu-only`）
- **THEN** 跳过对 `FEISHU_SHEETS_CONFIG.enabled` 的检查，仍校验 `folder_token` 等必填项；若必填项满足则执行同步
