# Tasks: 修复复盘数据为空——基于 strategy_recommendations 必生成 review_summary

- [x] 1.1 修改 `autoreview/review_cache.py`：`save_review_summary` 的 `recommendation_price` 改为 `Optional[float]`，None 时 INSERT 写 NULL。
- [x] 1.2 修改 `autoreview/auto_review.py`：`auto_review_last_n_days` 中，复盘范围改为「当日 + 过去 N 个交易日」；`dates_to_process = [trade_date_today] + trading_dates`，并统一循环处理，删除单独当日占位块。
- [x] 1.3 在统一循环中：当日推荐一律占位，`recommendation_price` 为 None 也写入；历史日：有 `recommendation_price` 则算 `calculate_daily_scores` 并保存，否则占位（`recommendation_price=None`）。
- [x] 1.4 当 `trading_dates` 为空时不再 `return`，仅打印提示并继续处理当日推荐。
