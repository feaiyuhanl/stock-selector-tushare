## 1. 复盘流程与推荐记录

- [x] 1.1 在 `stock_selector.py` 中，每次执行选股并调用 `_save_recommendations` 后，对**本次运行所涉的每个策略**，使用 `get_analysis_date()` 的 `trade_date` 作为“当日”，确认当日推荐已写入 `strategy_recommendations`（已有 `_save_recommendations` 即满足“自动更新记录当日最新推荐”）。
- [x] 1.2 在 `stock_selector.py` 中，选股与保存推荐之后、在发送通知之前，调用复盘流程：对**前 N 个交易日**（`AUTO_REVIEW_CONFIG.review_days`，不含当日）执行 `auto_review_last_n_days(days=N)`；combined 模式下对两个策略各保存推荐后，**共调用一次** `auto_review_last_n_days`（因该函数会按 `strategy_recommendations` 中的 `strategy_name` 分组处理所有策略）。
- [x] 1.3 在 `autoreview/auto_review.py` 的 `review_single_date` 中，对每条 `(trade_date, strategy_name, stock_code)` 在计算并保存前先调用 `review_cache.check_review_exists`；若为 True 则**跳过**该条（不调用 `save_review_summary`），从而“复盘完成或是有结果，无需重复复盘”。
- [x] 1.4 在 `autoreview/auto_review.py` 的 `_get_trading_dates_before` 中，确保“前 N 个交易日”不包含 `get_analysis_date()` 的当天（即 end_date 取“昨日”或“当前分析日的前一交易日”的语义与现有实现一致）；如需，在入口用 `get_analysis_date()` 或“昨日”作为 `end_date`，保证与“当日只写推荐、不做复盘”一致。
- [x] 1.5 在 `config.py` 的 `AUTO_REVIEW_CONFIG` 中补充或确认：`review_days`、`enabled`、`auto_update` 等；如需“仅跳过已有、不自动补齐历史”的独立开关，可加可选 `skip_existing_only`（本提案默认：只要有 `check_review_exists` 为 True 即跳过，不需要额外配置）。

## 2. 飞书电子表格同步

- [x] 2.1 在 `config.py` 中新增 `FEISHU_SHEETS_CONFIG`：`enabled`（默认 False）、`folder_token`、`app_id`、`app_secret`；支持从环境变量读取（如 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_FOLDER_TOKEN`）。
- [x] 2.2 新建 `integrations/feishu_sheets.py`（或 `notifications/feishu_sheets.py`）：实现 `get_tenant_access_token(app_id, app_secret)`；实现 `create_spreadsheet(title, folder_token)`，调用 `POST /open-apis/sheets/v3/spreadsheets`，Body `{"title","folder_token"}`，返回 `spreadsheet_token`；**不使用** `drive/v1/files`。
- [x] 2.3 在 `feishu_sheets` 模块中实现：`find_spreadsheet_by_title(folder_token, title)` 或等价逻辑（通过 drive 查询文件夹子文件按 `title` 匹配，若飞书 API 支持）；或实现“按 `strategy_name` + 年份 生成 `title`，先尝试创建；若返回 409/已存在，则通过 drive 搜索/子文件列表按 title 获取 `spreadsheet_token`”。二者择一即可；若首版简化，可只做“每次创建新表”（需避免同名冲突策略，如 title 加时间戳或由产品决定）。
- [x] 2.4 实现 `write_review_to_sheet(spreadsheet_token, df: DataFrame)`：将 `df` 的列作为表头，行作为数据，通过飞书 Sheets 的 **values 写入接口**（如 `PUT /open-apis/sheets/v2/spreadsheets/{spreadsheetToken}/values/{range}` 或 v3 等价）写入；`df` 的列与 `review_summary` 的导出列或 `get_review_summary` 的 DataFrame 一致（或与策略推荐+复盘内容一致的列子集），具体列在 spec 中约定。
- [x] 2.5 实现 `sync_review_to_feishu(strategy_name: str, review_df: pd.DataFrame, folder_token: str, feishu_config: dict)`：生成 `title = "{YYYY}_{strategy_name}_复盘结果"`；若不存在则 `create_spreadsheet`，若存在则取 `spreadsheet_token`；调用 `write_review_to_sheet`。失败时打日志，不抛错中断主流程；可重试 1～2 次。
- [x] 2.6 在 `stock_selector.py` 的复盘流程结束后，若 `FEISHU_SHEETS_CONFIG.enabled` 为 True 且 `folder_token` 非空：对本轮涉及的每个 `strategy_name`，从 `ReviewCache.get_review_summary(strategy_name=strategy_name)` 拉取该策略的复盘数据（可按 `recommendation_date` 等过滤最近范围）；若非空则调用 `sync_review_to_feishu`。combined 模式下对 `ScoringStrategy`、`IndexWeightStrategy` 各同步一次（若各自有复盘数据）。

## 3. 集成与配置

- [x] 3.1 在 `stock_selector.py` 中，复盘逻辑与飞书同步的调用顺序为：选股 → `_save_recommendations` → `auto_review_last_n_days`（内部已按 `check_review_exists` 跳过已有）→ 若 `FEISHU_SHEETS_CONFIG.enabled` 则按策略 `sync_review_to_feishu` → 再执行通知（如有）。
- [x] 3.2 在 `docs/review.md` 中补充：四个优化点的说明；飞书同步开关、`FEISHU_SHEETS_CONFIG` 的配置项与环境变量；飞书应用权限（`drive:drive`、`sheets:spreadsheet`、创建电子表格）及 `folder_token` 的获取方式。
- [x] 3.3 添加或更新 `requirements.txt`：若使用 `requests` 调用飞书 API，确认已包含；如有飞书官方 SDK 且采用，则加入对应依赖。

## 4. 校验与测试

- [ ] 4.1 单测或手工：`check_review_exists` 为 True 时，`review_single_date` 内不写入 `save_review_summary`，且 `auto_review_last_n_days` 的“更新”计数不增加该项。
- [ ] 4.2 单测或手工：`FEISHU_SHEETS_CONFIG.enabled=False` 或 `folder_token` 为空时，不调用飞书相关代码；`enabled=True` 且配置正确时，能创建表格并写入与 `review_summary` 列一致的数据（或约定列子集）。
- [ ] 4.3 运行 `openspec validate refactor-review-and-feishu-sheets --strict --no-interactive`，通过后交付。
