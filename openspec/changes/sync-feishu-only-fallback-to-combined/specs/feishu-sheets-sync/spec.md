## MODIFIED Requirements

### Requirement: 临时测试参数仅同步复盘结果到飞书

系统 SHALL 提供临时测试参数 `--sync-feishu-only`：优先从本地 `review_summary`（经 `ReviewCache.get_review_summary`）读取已有复盘结果，按策略（如 `ScoringStrategy`、`IndexWeightStrategy`）同步到飞书电子表格。此模式下不检查 `FEISHU_SHEETS_CONFIG.enabled`，但仍需 `folder_token`、`app_id`、`app_secret` 已配置，否则提示错误并退出。

- **有复盘数据时**：不执行选股、不执行复盘，仅读取 `review_summary` 并同步。
- **无复盘数据时**：对两策略 `get_review_summary` 若**都**为 `None` 或 empty，则先自动执行 **combined 策略**（选股 + 保存推荐 + `auto_review_last_n_days` 复盘），再执行飞书同步；若任一侧有数据，则仅同步，不选股、不复盘。

#### Scenario: 仅同步不选股不复盘（有复盘数据）

- **WHEN** 用户执行 `python stock_selector.py --sync-feishu-only` 且 `ScoringStrategy` 或 `IndexWeightStrategy` 至少一侧在 `review_summary` 中有数据
- **THEN** 程序不运行选股、不运行 `auto_review_last_n_days`；使用 `CacheManager` 与 `ReviewCache` 从本地 DB 读取 `review_summary`，按策略调用 `_run_feishu_sync(..., force=True)` 将结果同步到飞书；完成后退出

#### Scenario: 无复盘数据时自动执行 combined 并复盘后再同步

- **WHEN** 用户执行 `python stock_selector.py --sync-feishu-only` 且对 `ScoringStrategy`、`IndexWeightStrategy` 的 `get_review_summary(strategy_name=sn)` **两者都**返回 `None` 或 empty
- **THEN** 先输出「本地无复盘数据，正在自动执行 combined 选股与复盘…」；通过 `check_tushare_token` 后，自动执行 combined 策略（两策略选股、保存推荐、`auto_review_last_n_days` 复盘），再使用同一 `cache_manager` 调用 `_run_feishu_sync(..., force=True)` 同步到飞书；不执行通知、不在此前单独调用主流程的飞书同步

#### Scenario: 未配置飞书必填项时退出

- **WHEN** `--sync-feishu-only` 且 `folder_token` 或 `app_id`/`app_secret` 未配置
- **THEN** 打印对应错误提示并 `sys.exit(1)`，不发起同步、不执行选股或复盘

#### Scenario: force 模式跳过 enabled 检查

- **WHEN** `_run_feishu_sync` 被以 `force=True` 调用（如来自 `--sync-feishu-only`）
- **THEN** 跳过对 `FEISHU_SHEETS_CONFIG.enabled` 的检查，仍校验 `folder_token` 等必填项；若必填项满足则执行同步
