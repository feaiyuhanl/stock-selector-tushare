# Change: --sync-feishu-only 在本地无复盘数据时自动执行 combined 策略并复盘后再同步

## Why

用户使用 `--sync-feishu-only` 时，若本地尚未跑过选股+复盘，`review_summary` 为空，会得到「无复盘数据，跳过」的提示，需要先手动执行 `python stock_selector.py --factor-set combined` 再执行 `--sync-feishu-only`。希望简化：当检测到**本地没有任何复盘数据**时，自动先执行 combined 策略（选股 + 保存推荐 + 自动复盘），完成后再执行飞书同步，一步到位。

## What Changes

- **MODIFIED** `--sync-feishu-only` 行为：
  - **有复盘数据时**：保持原行为——不执行选股、不执行复盘，仅从 `review_summary` 读取并按策略同步到飞书。
  - **无复盘数据时**：先自动执行 **combined 策略**（两策略选股、保存推荐、`auto_review_last_n_days` 复盘），再使用同一 `cache_manager` 调用 `_run_feishu_sync(..., force=True)` 同步到飞书。无复盘数据的判定：对 `ScoringStrategy`、`IndexWeightStrategy` 分别 `get_review_summary(strategy_name=sn)`，若**两者都**返回 `None` 或 empty，则视为无复盘数据；若任一侧有数据，则不自动跑 combined，仅同步。
- **REMOVED**：在「无复盘数据」且走自动 combined 的场景下，不再输出提示「请先运行选股并执行自动复盘…再使用 --sync-feishu-only」；可改为输出「[飞书同步] 本地无复盘数据，正在自动执行 combined 选股与复盘…」等进度说明。

## Impact

- **Affected specs**：`feishu-sheets-sync`（MODIFIED：`--sync-feishu-only` 的 Requirement 及 Scenario）
- **Affected code**：
  - `stock_selector.py`：`_handle_sync_feishu_only` 在配置校验通过后、调用 `_run_feishu_sync` 之前，先用 `ReviewCache.get_review_summary` 检测两策略是否均有数据；若均无，则调用 `check_tushare_token`，通过后执行与 `main` 中 combined 分支等价的「选股 + 保存推荐 + 自动复盘」流程（不含打印结果、通知、飞书同步），取得 `cache_manager`，再 `_run_feishu_sync(cache_manager, [...], force=True)`。可选：将 combined 的「选股+保存+复盘」抽取为 `_run_combined_selection_and_review(args) -> cache_manager` 供 `main` 与 `_handle_sync_feishu_only` 复用；若为最小改动，可在 `_handle_sync_feishu_only` 内联实现，并构造 `args`（`factor_set=combined` 及 `config` 默认值，如 `refresh=False`、`top_n=config.TOP_N`、`board=None`/`config.DEFAULT_BOARD_TYPES`、`workers=config.DEFAULT_MAX_WORKERS`、`indices=None`、`lookback_days=None` 等）。
  - `_run_feishu_sync` 内「force 且 any_with_data 为 False」时原「提示：本地尚无复盘数据…」的打印可删除或改为仅在「未触发自动 combined」时保留（本 change 下，`_handle_sync_feishu_only` 在无数据时会先跑 combined，故进入 _run_feishu_sync 时理论上已有数据；若仍无，可保留一版短提示）。
  - `docs/review.md`：更新 `--sync-feishu-only` 说明，注明「若本地无复盘数据，会自动执行 combined 选股与复盘后再同步」；原 Troubleshooting 中「先 combined 再 --sync-feishu-only」的两步说明可弱化或改为「若未自动触发 combined，可先手动运行 combined」。
  - `openspec/changes/optimize-review-and-feishu-flow/proposal.md`：Troubleshooting 中关于「无复盘数据」的解决步骤可更新为「或直接使用 --sync-feishu-only，程序会在无数据时自动执行 combined 并复盘后同步」。
