## 1. 无复盘数据判定与 fallback 入口

- [x] 1.1 在 `_handle_sync_feishu_only` 内，配置校验通过后、`print("[飞书同步] 开始…")` 之前，使用 `CacheManager()` 与 `ReviewCache`，对 `ScoringStrategy`、`IndexWeightStrategy` 分别 `get_review_summary(strategy_name=sn)`；若**两者都**为 `None` 或 `df.empty`，则置 `needs_combined = True`，否则 `needs_combined = False`。
- [x] 1.2 当 `needs_combined` 为 True 时：先 `print("[飞书同步] 本地无复盘数据，正在自动执行 combined 选股与复盘…")`，再调用 `check_tushare_token()`，未通过则 `sys.exit(1)`；通过后执行 combined 选股+保存+复盘流程（见下），取得 `cache_manager`，再执行 `_run_feishu_sync(cache_manager, ['ScoringStrategy','IndexWeightStrategy'], force=True)` 与 `print("[飞书同步] 完成")`，然后 `return`。当 `needs_combined` 为 False 时，保持原有逻辑：`print("[飞书同步] 开始…")`、`_run_feishu_sync`、`print("[飞书同步] 完成")`。

## 2. 在 _handle_sync_feishu_only 内实现 combined 选股+保存+复盘

- [x] 2.1 构造 `args`：`argparse.Namespace`，包含 `factor_set='combined'`，以及 `refresh=False`、`strategy='multi_factor'`、`top_n=config.TOP_N`、`board=None`、`workers=config.DEFAULT_MAX_WORKERS`、`indices=None`、`lookback_days=None`、`stocks=None` 等，以适配 `_create_strategy`、`_prepare_select_params`。
- [x] 2.2 复用 `_create_strategy`、`_prepare_select_params`、`_execute_selection`、`_save_recommendations`、`print_results`：对 `factor_set='fundamental'` 与 `'index_weight'` 的副本 args 分别创建策略、选股、打印结果、保存推荐；然后若 `config.AUTO_REVIEW_CONFIG.get('enabled', True)` 则 `AutoReview( selector_fundamental.strategy.data_fetcher, selector_fundamental.strategy.data_fetcher.cache_manager ).auto_review_last_n_days()`。不执行 `_run_feishu_sync`、不执行通知。`cache_manager` 取自 `selector_fundamental.strategy.data_fetcher.cache_manager`。

## 3. _run_feishu_sync 与文档

- [x] 3.1 在 `_run_feishu_sync` 中，当 `force and not any_with_data` 时：将原长提示「请先运行选股并执行自动复盘…」简化为一句短提示（如「[飞书同步] 同步完成，各策略均无复盘数据。」），或删除（因 `_handle_sync_feishu_only` 在无数据时会先跑 combined，正常不会进入此分支）；若保留，需与 1.2 的「自动执行 combined」语义不冲突。
- [x] 3.2 在 `docs/review.md` 的 `--sync-feishu-only` 说明中补充：若本地无 `ScoringStrategy`、`IndexWeightStrategy` 任一复盘数据，会先自动执行 combined 选股与复盘，再同步；原两步说明可弱化。
- [x] 3.3 在 `openspec/changes/optimize-review-and-feishu-flow/proposal.md` 的 Troubleshooting 中，将「先 combined 再 --sync-feishu-only」增补为：或直接使用 `--sync-feishu-only`，无数据时会自动执行 combined 并复盘后同步。

## 4. 校验

- [x] 4.1 运行 `openspec validate sync-feishu-only-fallback-to-combined --strict --no-interactive` 通过。
