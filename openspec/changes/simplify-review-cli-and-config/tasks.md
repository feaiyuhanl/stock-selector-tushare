## 1. 配置

- [x] 1.1 在 `config.py` 的 `AUTO_REVIEW_CONFIG` 中新增 `review_start_date`（默认 `None`，示例 `"20240101"`）；保留 `enabled`、`review_days`（默认 10）、`auto_update`。

## 2. 复盘逻辑

- [x] 2.1 在 `autoreview/auto_review.py` 的 `auto_review_last_n_days` 中，在得到 `trading_dates` 后，读取 `review_start_date = (config.AUTO_REVIEW_CONFIG.get('review_start_date') or '').strip() or None`，若非空则 `trading_dates = [d for d in trading_dates if d >= review_start_date]`。
- [x] 2.2 移除或保留 `fill_missing_reviews`：若不再被调用则删除；否则保留不调用。

## 3. CLI 与主流程

- [x] 3.1 在 `stock_selector.py` 的 `argparse` 中移除 `--no-auto-review`、`--fill-review-gaps`、`--review-days`；保留 `--review`、`--review-date`。
- [x] 3.2 移除 `_handle_fill_review_gaps` 以及 `if args.fill_review_gaps: _handle_fill_review_gaps(); return` 分支。
- [x] 3.3 在 `_handle_review_command` 中，`days` 改为 `config.AUTO_REVIEW_CONFIG.get('review_days', 10)`，不再使用 `args.review_days`。
- [x] 3.4 主流程（combined 与 单策略）中，将 `if not args.no_auto_review and config.AUTO_REVIEW_CONFIG.get('enabled', True)` 改为 `if config.AUTO_REVIEW_CONFIG.get('enabled', True)`；飞书同步逻辑不变，仍由 `_run_feishu_sync` 内部根据 `FEISHU_SHEETS_CONFIG.enabled` 判断。

## 4. 文档与校验

- [x] 4.1 在 `docs/review.md` 中更新：复盘/飞书由 config 控制；`review_start_date`、`review_days` 说明；已移除的 CLI 参数说明。
- [x] 4.2 运行 `openspec validate simplify-review-cli-and-config --strict --no-interactive` 通过。
