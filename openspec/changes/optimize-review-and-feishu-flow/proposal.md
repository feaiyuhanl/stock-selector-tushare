# Change: 优化复盘与飞书流程：简化 CLI、选股即复盘即飞书、新增仅同步测试参数

## Why

1. 复盘相关 CLI 参数（`--review-days`、`--fill-review-gaps`、`--no-auto-review`）增加使用成本，且与 config 重复；希望默认复盘最近 10 个交易日，其余可配置项统一在 `config.py` 的 `AUTO_REVIEW_CONFIG` 等模块实现，不再提供对应命令行参数。
2. 希望「每次执行选股 → 自动执行复盘 → 复盘完成后自动同步到飞书列表」，流程固定、由 config 开关控制，无需额外 CLI。
3. 需要临时测试参数：仅将本地已有复盘结果同步到飞书，不重新跑选股、不重新跑复盘，便于单独验证飞书同步功能。

## What Changes

- **MODIFIED**: 复盘相关 CLI 仅保留 `--review`、`--review-date`（用于按需查看指定日期的复盘报告）。**移除** `--review-days`、`--fill-review-gaps`、`--no-auto-review`。复盘天数（默认 10）、起始日期、是否自动复盘、是否自动补齐等均通过 `config.AUTO_REVIEW_CONFIG` 配置；`_handle_review_command` 的 `days` 从 `config.AUTO_REVIEW_CONFIG.get('review_days', 10)` 读取。
- **MODIFIED**: 选股流程：每次选股保存推荐后，若 `AUTO_REVIEW_CONFIG.enabled` 为 True 则自动执行 `auto_review_last_n_days`；复盘完成后，若 `FEISHU_SHEETS_CONFIG.enabled` 为 True 且 `folder_token` 等已配置，则自动调用 `_run_feishu_sync` 按策略同步到飞书。无新增选股/复盘/飞书相关的流程 CLI，仅由 config 控制。
- **ADDED**: 临时测试参数 `--sync-feishu-only`：不执行选股、不执行复盘；从本地 `review_summary`（经 `ReviewCache.get_review_summary`）读取已有复盘结果，按策略（如 `ScoringStrategy`、`IndexWeightStrategy`）同步到飞书。此模式下不检查 `FEISHU_SHEETS_CONFIG.enabled`，以便在 `enabled=False` 时也能测试同步；但仍需 `folder_token`、`app_id`、`app_secret` 等已配置，否则提示并退出。

## Troubleshooting: `--sync-feishu-only` 报「无复盘数据，跳过」

**根因**：`--sync-feishu-only` 只从本地 `review_summary` 表读取已有复盘数据并同步到飞书，**不会执行选股，也不会执行复盘**，因此不会写入任何新数据。

`review_summary` 的写入链路：**选股** → `_save_recommendations`（写入 `strategy_recommendations`）→ **自动复盘** `auto_review_last_n_days`（从 `strategy_recommendations` 读推荐，计算表现并写入 `review_summary`）。若从未跑过「选股 + 自动复盘」完整流程，或复盘被关闭、或对应交易日没有推荐数据，`review_summary` 中就不会有 `ScoringStrategy` / `IndexWeightStrategy` 的记录，`get_review_summary(strategy_name=sn)` 返回空，从而出现「无复盘数据，跳过」。

**解决步骤**：

- **推荐**：直接使用 `--sync-feishu-only`，程序会在检测到本地无复盘数据时**自动执行 combined 选股与复盘**，完成后再同步到飞书。
- 或分两步：先 `python stock_selector.py --factor-set combined`（且 `config.AUTO_REVIEW_CONFIG.enabled` 为 `True`），再 `python stock_selector.py --sync-feishu-only`。

**可选诊断**：检查本地库中是否已有复盘数据及策略名：

```bash
# 若 DB 在项目下 cache 目录
sqlite3 cache/stock_cache.db "SELECT strategy_name, COUNT(*) FROM review_summary GROUP BY strategy_name;"
```

若输出为空或没有 `ScoringStrategy`、`IndexWeightStrategy`，说明需先跑选股+复盘。

## Impact

- **Affected specs**: `review`，`feishu-sheets-sync`
- **Affected code**:
  - `stock_selector.py`：移除 `--review-days`、`--fill-review-gaps`、`--no-auto-review`；移除与 `args.fill_review_gaps`、`args.no_auto_review`、`args.review_days` 相关的分支；`_handle_review_command` 的 `days` 改为 `config.AUTO_REVIEW_CONFIG.get('review_days', 10)`；新增 `--sync-feishu-only` 及其处理逻辑（创建 `CacheManager`、`ReviewCache`，按策略调用同步，`_run_feishu_sync` 增加 `force` 参数以在此模式下跳过 `enabled` 检查）；主流程中复盘条件保持 `config.AUTO_REVIEW_CONFIG.get('enabled', True)`，飞书同步仍由 `_run_feishu_sync` 内部根据 `FEISHU_SHEETS_CONFIG.enabled` 判断。
  - `integrations/feishu_sheets.py` 或 `stock_selector._run_feishu_sync`：`_run_feishu_sync` 增加可选参数 `force: bool = False`，当 `force=True` 时跳过对 `FEISHU_SHEETS_CONFIG.enabled` 的检查，仍校验 `folder_token` 等必填项。
  - `config.py`：无结构性变更；`AUTO_REVIEW_CONFIG.review_days`（默认 10）、`review_start_date`、`enabled` 及 `FEISHU_SHEETS_CONFIG` 已满足需求。
