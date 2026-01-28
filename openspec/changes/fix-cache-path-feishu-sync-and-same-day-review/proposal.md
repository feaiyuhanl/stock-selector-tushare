# Change: 修复 cache 相对路径导致飞书同步读错库、当日复盘占位、get_review_summary 诊断

## Why

1. **本地 SQLite 有复盘数据，飞书同步却报「无复盘数据」**：`CacheManager` 使用相对路径 `cache_dir="cache"`，`db_path = "cache/stock_cache.db"` 随进程 CWD 变化。选股/复盘在项目根跑时写入 `项目根/cache/stock_cache.db`；从其它目录或 IDE 启动 `--sync-feishu-only` 或飞书同步时，会连接 `其他目录/cache/stock_cache.db`，读不到已有数据。此外，若 `review_summary` 中 `strategy_name` 与 `'ScoringStrategy'`/`'IndexWeightStrategy'` 不一致，精确匹配也会得到空，且目前无诊断手段。
2. **非交易日/当日有推荐，复盘与飞书却缺这一天的记录**：`get_analysis_date()` 在非交易日返回最近交易日，推荐会保存；但 `auto_review_last_n_days` 的 `end_date = get_analysis_date() - 1 天`，复盘范围不包含当日/最近交易日，故不会写入 `review_summary`。用户期望：至少保留当日/最近交易日的一组推荐作为复盘占位，`day1`–`day10`、最新价打分为空即可。

## What Changes

- **MODIFIED** `cache_dir` / `db_path`：将 `cache_dir` 改为基于**项目根**的绝对路径（如 `os.path.join(项目根, 'cache')`）。在 `config` 中新增 `CACHE_DIR` 或等价项，`CacheBase`/`CacheManager` 默认使用；`FetcherBase`、`_handle_sync_feishu_only` 等创建 `CacheManager()` 时保持不传参或从 config 读取，确保选股、复盘、飞书同步读写**同一** `stock_cache.db`，与 CWD 无关。
- **MODIFIED** `autoreview/auto_review.py`：在 `auto_review_last_n_days` 中，对 **`get_analysis_date()` 对应的 `trade_date`**（当日/最近交易日）：若该日在 `strategy_recommendations` 有推荐，且 `review_summary` 中尚无对应 `(trade_date, strategy_name, stock_code)`，则写入**占位复盘**：`recommendation_date`、`strategy_name`、`strategy_type`、`stock_code`、`stock_name`、`recommendation_price`、`rank` 来自推荐，`day1_price`–`day10_price`、`day1_score`–`day10_score`、`average_score`、`total_score` 置 `NULL`，`valid_days=0`。这样当日/非交易日也有至少一条可同步到飞书的记录，最新价打分为空符合预期。
- **MODIFIED** `autoreview/review_cache.py` 或 `_run_feishu_sync` 调用处：当 `get_review_summary(strategy_name=sn)` 返回 `None` 或 `df.empty` 且为飞书同步路径时，执行 `SELECT DISTINCT strategy_name FROM review_summary` 并打印或打日志，便于发现 `strategy_name` 与 `'ScoringStrategy'`/`'IndexWeightStrategy'` 不一致。可选：在「各策略均无复盘数据」时打印当前使用的 `db_path`（绝对），便于用户核对是否与本地查看的 DB 一致。
- **MODIFIED** `ReviewCache.save_review_summary` 或新增 helpers：支持 `daily_prices`/`daily_scores` 为空或 `valid_days=0` 时写入占位记录（`day1`–`day10` 等为 `NULL`），供当日复盘占位使用。

## Impact

- **Affected specs**：`review`（复盘范围扩展：含当日/最近交易日占位），`feishu-sheets-sync`（无 spec 变更，仅实现）
- **Affected code**：
  - `config`：新增 `CACHE_DIR`（或等价）指向项目根下 `cache` 的绝对路径
  - `data/cache_base.py`：`CacheBase.__init__` 默认 `cache_dir` 从 config 或 `os.path` 推导的绝对路径
  - `data/cache_manager.py`：`CacheManager` 透传 `cache_dir`，若未传入则使用 config/默认绝对路径
  - `data/fetcher_base.py`：保持 `CacheManager()` 无参或从 config 读，确保与全局一致
  - `autoreview/auto_review.py`：`auto_review_last_n_days` 增加对 `get_analysis_date()` 对应日期的占位复盘逻辑；`review_helper`/`review_cache.save_review_summary` 需支持 `valid_days=0`、`day1`–`day10` 为 `NULL` 的写入
  - `autoreview/review_cache.py`：`save_review_summary` 允许 `daily_prices`/`daily_scores` 为空时写入 `NULL`；可选：在 `get_review_summary` 或 `_run_feishu_sync` 侧增加「无数据时查 `DISTINCT strategy_name` 并打印」的诊断
  - `stock_selector._run_feishu_sync`：在「各策略均无复盘数据」时，可选打印 `cache_manager.db_path` 及 `review_summary` 中 `DISTINCT strategy_name`，便于排查
