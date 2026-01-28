## 1. cache 绝对路径

- [x] 1.1 在 `config` 中新增 `CACHE_DIR`：`os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')`，或基于项目根推导，确保为绝对路径。
- [x] 1.2 在 `data/cache_base.py` 的 `CacheBase.__init__` 中，当 `cache_dir` 为默认或未传入时，使用 `getattr(config, 'CACHE_DIR', None) or os.path.join(..., 'cache')` 等得到绝对路径，再赋给 `self.cache_dir` 与 `self.db_path`。
- [x] 1.3 在 `data/cache_manager.py` 的 `CacheManager.__init__` 中，若 `cache_dir="cache"` 或未传，则改为从 config 读取 `CACHE_DIR` 或等价的绝对路径；`data/fetcher_base.py` 的 `CacheManager()` 保持不传参，由 CacheManager 使用 config 默认。

## 2. 当日/最近交易日复盘占位

- [x] 2.1 在 `autoreview/review_cache.py` 的 `save_review_summary` 中，允许 `daily_prices`、`daily_scores` 为空或 `valid_days=0`：此时 `day1_price`–`day10_price`、`day1_score`–`day10_score`、`average_score`、`total_score` 写 `NULL`，其它字段正常。
- [x] 2.2 在 `autoreview/auto_review.py` 的 `auto_review_last_n_days` 中，在既有「前 N 个交易日」复盘循环**之后**（或之前，视实现方便），增加对 **`trade_date_today = get_analysis_date().strftime('%Y%m%d')`** 的处理：用 `RecommendationCache.get_recommendations(trade_date_today)` 取推荐，对每条 `(trade_date_today, strategy_name, stock_code)` 若 `check_review_exists` 为 False，则调用 `review_helper.get_stock_close_price` 得 `recommendation_price`，再调用 `save_review_summary` 且 `daily_prices={}`、`daily_scores={}`、`average_score=None`、`total_score=None`、`valid_days=0`（或等价），写入占位复盘。若 `recommendation_price` 为 None 可跳过该条。
- [x] 2.3 若 `review_helper.calculate_daily_scores` 或 `save_review_summary` 当前强依赖 `daily_prices`/`daily_scores` 非空，则扩展接口或加分支，支持「占位」写入。

## 3. get_review_summary 与飞书同步诊断

- [x] 3.1 在 `_run_feishu_sync` 中，当某 `sn` 的 `get_review_summary(strategy_name=sn)` 为 `None` 或 `df.empty` 时：用同一 `review_cache` 或 direct SQL 执行 `SELECT DISTINCT strategy_name FROM review_summary`，若结果非空则打印 `[飞书同步] 诊断: review_summary 中的 strategy_name 有: …`，便于用户核对是否与 `ScoringStrategy`/`IndexWeightStrategy` 一致。
- [x] 3.2 当 `force and not any_with_data` 时，在「各策略均无复盘数据」提示后，增加一行打印 `[飞书同步] 使用的 DB: {cache_manager.db_path}`（已为绝对路径），便于用户核对是否与本地查看的 SQLite 文件一致。

## 4. 校验与文档

- [x] 4.1 运行 `openspec validate fix-cache-path-feishu-sync-and-same-day-review --strict --no-interactive` 通过（若本 change 含 spec 增量）。
- [x] 4.2 在 `docs/review.md` 中补充：飞书同步与选股/复盘使用同一 `config.CACHE_DIR` 下的 `stock_cache.db`；若遇「无复盘数据」可检查 `strategy_name` 是否为 `ScoringStrategy`/`IndexWeightStrategy`，以及 `db_path` 是否与本地查看的 DB 一致。
