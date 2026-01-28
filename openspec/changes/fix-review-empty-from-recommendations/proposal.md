# Change: 修复复盘数据为空——基于 strategy_recommendations 必生成 review_summary

## Why

1. **推荐有、复盘无**：`strategy_recommendations` 已有推荐（含当日与历史），但 `review_summary` 为空，飞书同步报「无复盘数据」。用户期望：**推荐结果必定不为空时，复盘数据一定可以基于推荐数据生成一份最新的复盘结果**。
2. **复盘范围过窄**：原逻辑只复盘「过去 N 个交易日」（不含当日），且按 `get_recommendations(trade_date)` 按日取数。若用户只跑过选股一次，所有推荐的 `trade_date` 均为当日，前 N 天循环全部为空，只有「当日占位」会处理当日；而当日占位又要求 `get_stock_close_price` 非空，取不到则跳过，导致 0 条写入。
3. **占位依赖收盘价**：当日占位与历史日复盘在 `get_stock_close_price` 为 None 时直接 `continue`，不写入。若 K 线缺推荐日数据，整条推荐无法落盘，违反「有推荐即有复盘」的预期。

## What Changes

- **MODIFIED** `autoreview/auto_review.py` — `auto_review_last_n_days`：
  - **复盘范围**：由「仅过去 N 个交易日」改为 **当日 + 过去 N 个交易日**。`dates_to_process = [get_analysis_date().strftime('%Y%m%d')] + trading_dates`，确保 `strategy_recommendations` 中当日的推荐一定会被处理。
  - **统一循环**：删除单独的「当日/最近交易日占位」块，与「过去 N 日」复盘合并为同一循环；对 `dates_to_process` 中每个 `trade_date` 调用 `get_recommendations(trade_date)`，对每条「有推荐且无复盘」的 `(trade_date, strategy_name, stock_code)` 写入复盘或占位。
  - **占位不依赖 recommendation_price**：当日：一律占位（`daily_prices={}`, `daily_scores={}`, `valid_days=0`），`recommendation_price` 取 `get_stock_close_price` 结果，**为 None 也写入**。历史日：若 `get_stock_close_price` 非空则算 `calculate_daily_scores` 并写入完整复盘；若为空则写入占位（`recommendation_price=None`，day1–day10 等为 NULL）。从而**有推荐即必有一条 review_summary**。
  - **交易日为空**：当 `_get_trading_dates_before` 返回空时，不再 `return`，仅打印「未找到过去 N 个交易日数据，仅处理当日推荐。」，继续处理当日。
- **MODIFIED** `autoreview/review_cache.py` — `save_review_summary`：`recommendation_price` 改为 `Optional[float]`，为 `None` 时在 `review_summary` 中写 NULL，以支持「无 K 线时仍写占位」。

## 流程保证

- **默认执行顺序**（与既有设计一致）：**先生成推荐结果**（选股 + `_save_recommendations`）→ **基于推荐结果复盘**（`auto_review_last_n_days`，现覆盖当日 + 过去 N 日）→ **复盘结果同步飞书**（`_run_feishu_sync`）。无需新增 CLI，由 `AUTO_REVIEW_CONFIG.enabled`、`FEISHU_SHEETS_CONFIG.enabled` 控制。

## Impact

- **Affected specs**: `review`
- **Affected code**:
  - `autoreview/auto_review.py`：复盘数据源、占位逻辑、去重与循环
  - `autoreview/review_cache.py`：`save_review_summary(recommendation_price: Optional[float])`
