## 1. CLI 复盘参数精简

- [x] 1.1 在 `stock_selector.py` 的 `argparse` 中移除 `--review-days`、`--fill-review-gaps`、`--no-auto-review`；保留 `--review`、`--review-date`。
- [x] 1.2 在 `_handle_review_command` 中，将 `days` 改为 `config.AUTO_REVIEW_CONFIG.get('review_days', 10)`，移除对 `args.review_days` 的引用。
- [x] 1.3 移除所有对 `args.fill_review_gaps`、`args.no_auto_review` 的分支（若存在 `_handle_fill_review_gaps` 或类似逻辑则一并删除）。

## 2. 选股后自动复盘与飞书同步

- [x] 2.1 确认选股主流程（单策略与 combined）：保存推荐后，当 `config.AUTO_REVIEW_CONFIG.get('enabled', True)` 时调用 `auto_review_last_n_days`；复盘完成后，`_run_feishu_sync` 内部根据 `FEISHU_SHEETS_CONFIG.enabled` 及 `folder_token` 决定是否同步。若无则按此逻辑实现。
- [x] 2.2 确保 `_run_feishu_sync` 在复盘逻辑之后、通知之前被调用，且不阻塞主流程（异常时打印警告）。

## 3. 仅同步飞书测试参数

- [x] 3.1 在 `argparse` 中新增 `--sync-feishu-only`（`action='store_true'`，help 注明：临时测试，仅将本地复盘结果同步到飞书，不执行选股与复盘）。
- [x] 3.2 在 `_run_feishu_sync` 中增加可选参数 `force: bool = False`；当 `force=True` 时跳过对 `FEISHU_SHEETS_CONFIG.enabled` 的检查，仍校验 `folder_token`、`app_id`、`app_secret` 等；若必填项缺失则 return 并打印提示。
- [x] 3.3 实现 `--sync-feishu-only` 分支：在解析参数后、选股/复盘之前，若 `args.sync_feishu_only` 则：使用 `CacheManager()` 与 `ReviewCache`，对策略列表 `['ScoringStrategy','IndexWeightStrategy']` 依次 `get_review_summary(strategy_name=sn)`，若 `df` 非空则调用 `sync_review_to_feishu`（或通过 `_run_feishu_sync(..., force=True)` 复用逻辑）；若 `folder_token` 等未配置则打印错误并 `sys.exit(1)`。完成后 `return`，不进入选股流程。

## 4. 文档与校验

- [x] 4.1 在 `docs/review.md`（或等价文档）中补充：复盘与飞书由 config 控制；已移除的 `--review-days`、`--fill-review-gaps`、`--no-auto-review` 说明；`--sync-feishu-only` 的用途与用法。
- [x] 4.2 运行 `openspec validate optimize-review-and-feishu-flow --strict --no-interactive` 通过。
