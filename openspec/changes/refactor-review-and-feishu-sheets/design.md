# Design: 复盘优化与飞书电子表格同步

## Context

复盘功能用于评估策略推荐的实际表现，将结果写入 `review_summary`；推荐结果写入 `strategy_recommendations`。需要：（1）在每次运行任何策略后自动更新前几个交易日的复盘与当日推荐；（2）避免对已有复盘条目的重复计算；（3）通过开关将复盘结果同步到飞书电子表格，一个策略一个表格，命名 `YYYY_策略_复盘结果`，表格不存在时创建。飞书侧仅使用 **Sheets API**（`/open-apis/sheets/v3/spreadsheets` 创建、values 写入），不使用 `drive/v1/files` 或 文档/多维表格 接口。

## Goals / Non-Goals

### Goals

- 每次策略运行后，统一触发：保存当日推荐、更新前 N 个交易日的复盘（对已有记录跳过，对缺失或需更新的执行计算并写入）。
- 复盘逻辑与 `review_summary` 列结构保持不变；与 `strategy_recommendations` 的推荐记录一致。
- 飞书同步为可选开关；使用 `sheets/v3/spreadsheets` 创建表格，用 values 接口写入表头与数据；一个策略一个 spreadsheet，命名 `YYYY_策略_复盘结果`；若指定 `folder_token` 下不存在则创建。
- `folder_token` 支持非 `fld` 开头的格式（以飞书 API 实际为准）。

### Non-Goals

- 不变更 `review_summary`、`strategy_recommendations` 的表结构。
- 不使用飞书 `drive/v1/files`、文档、多维表格等非 Sheets 接口做复盘结果存储。
- 不实现飞书 OAuth 用户登录；仅使用应用 tenant 维度的 `tenant_access_token`（或文档要求的 token 类型）。

## Decisions

### Decision: 复盘触发时机与范围

- **行为**：在 `stock_selector.py` 中，**每次**执行选股（单个策略或 combined 下各策略）并在保存推荐之后，调用复盘流程；复盘范围 = **前 N 个交易日**（`AUTO_REVIEW_CONFIG.review_days`，如 10），不包含“当日”（当日只做推荐写入，不做过往 N 日的复盘计算，因当日尚未有后续交易日数据）。
- **当日推荐**：继续使用 `_save_recommendations`，按 `get_analysis_date()` 得到 `trade_date`，写入/覆盖 `strategy_recommendations`；视为“每次运行任何策略即更新并记录当日最新推荐”。
- **Rationale**：与需求“每次运行任何策略，支持自动更新前几个交易日的复盘”和“自动更新记录当日最新推荐结果”一致；前 N 日用 `_get_trading_dates_before(today, N)` 即可。

### Decision: 跳过已有复盘（不复盘已完成或有结果的日期条目）

- **粒度**：按 `(recommendation_date, strategy_name, stock_code)` 判断。若 `review_summary` 中已存在该三元组，则**跳过**该条，不再计算、不覆盖；仅对不存在或明确需要“重算”的条目执行 `save_review_summary`。
- **Rationale**：`review_cache.check_review_exists` 已存在；在 `review_single_date` / `auto_review_last_n_days` 的循环里，对每条 `(trade_date, strategy_name, stock_code)` 先 `check_review_exists`，为 True 则跳过，避免重复复盘。

### Decision: 飞书仅使用 Sheets API，创建与写入流程

- **创建**：`POST https://open.feishu.cn/open-apis/sheets/v3/spreadsheets`，Body `{"title":"<YYYY>_<StrategyName>_复盘结果","folder_token":"<folder_token>"}`。若接口返回 `spreadsheet_token`，则用于后续写入。
- **查找**：若需“按标题查找再决定是否创建”，可在 drive 的 `search` 或 文件夹子文件列表中按 `title` 匹配；若项目为简化实现，可採用“按命名规范生成 title，先尝试创建；若飞书返回“已存在/冲突”再走查找”的折中；**或** 在应用侧维护 `strategy_name -> spreadsheet_token` 的轻量映射（如配置或 cache 表），存在则只写入不创建。具体以 tasks 为准；此处规定：**创建必须使用 `sheets/v3/spreadsheets`，不得使用 `drive/v1/files` 创建表格**。
- **写入**：使用飞书 **Sheets 的 values 写入接口**（如 `PUT /open-apis/sheets/v2/spreadsheets/{spreadsheetToken}/values/{range}` 或 v3 的等价接口），将表头与 `review_summary` 导出行写入。列顺序、列名与策略推荐及复盘内容一致（即与 `review_summary` 的导出列或 `get_review_summary` 的 DataFrame 列一致）。
- **Rationale**：避免 `drive/v1/files` 曾导致的 404；与 [创建电子表格](https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet/create) 文档一致；`folder_token` 不以 `fld` 开头也有效。

### Decision: 飞书配置与开关

- **配置块**：`FEISHU_SHEETS_CONFIG`，包含：`enabled`（是否同步）、`folder_token`（目标文件夹 token）、`app_id`、`app_secret`（用于获取 `tenant_access_token`）。可选：`app_token` 若飞书文档要求。
- **开关**：当 `FEISHU_SHEETS_CONFIG.enabled` 为 True 且 `folder_token` 有效时，在复盘流程结束且生成本地 `review_summary` 后，对**本 run 所涉策略**的复盘结果执行同步；若 `enabled` 为 False 或 `folder_token` 为空，则不同步。
- **Rationale**：与“复盘结果额外增加一个开关”一致；实现可放在 `config.py`，通过环境变量覆盖 `app_id`、`app_secret`、`folder_token` 以利安全。

### Decision: 一个策略一个飞书表格，命名与列一致性

- **命名**：`<YYYY>_<StrategyName>_复盘结果`，例如 `2026_ScoringStrategy_复盘结果`。`YYYY` 为当前年份（或复盘数据所在年份，可统一为运行年份）；`StrategyName` 为 `strategy.get_strategy_name()` 的返回值。
- **列**：与“策略结果和复盘内容保持一致”；即写入飞书表格的列 = 复盘导出结构（如 `review_summary` 的列或 `get_review_summary` 返回的 DataFrame 列），及/或策略推荐中的关键字段（如 `code`、`name`、`rank`、`score` 等），具体列集在 `feishu-sheets-sync` spec 中规定；实现上应做到与本地复盘报告、`review_summary` 可对应。
- **Rationale**：需求明确“一个策略一个飞书表格”“表格命名方式：2026_策略_复盘结果”“策略结果和复盘内容保持一致”。

## 飞书 API 要点（实现时以官方文档为准）

| 用途 | 方法 | URL | 说明 |
|------|------|-----|------|
| 创建电子表格 | POST | `/open-apis/sheets/v3/spreadsheets` | Body: `{"title","folder_token"}`；返回 `data.spreadsheet.spreadsheet_token` |
| 写入/更新单元格 | PUT | `/open-apis/sheets/v2/spreadsheets/{spreadsheetToken}/values/{range}` 或 v3 等价 | 将表头+数据按 range 写入 |
| 鉴权 | POST | `/open-apis/auth/v3/tenant_access_token/internal` | `app_id`、`app_secret`，取 `tenant_access_token` |

权限：`drive:drive`，`sheets:spreadsheet`，创建电子表格。`folder_token` 格式不要求 `fld` 前缀。

## Risks / Trade-offs

- **飞书 API 限流/失败**：同步失败时记录日志，不阻塞复盘与本地保存；可重试 1～2 次，仍失败则跳过当次同步。
- **`folder_token` 失效**：若文件夹被删或权限收回，创建/写入会失败；通过日志与配置说明提示用户检查 `folder_token` 与应用权限。
- **表格已存在**：若先“创建”再写入，飞书可能因同名等返回错误；实现时需按“按标题查找 → 存在则取 token 只写入，不存在则创建再写入”或“维护 spreadsheet_token 映射”之一处理，见 tasks。

## Migration Plan

- 无 DB schema 变更；`AUTO_REVIEW_CONFIG` 增加配置项时保持向后兼容（新 key 默认 off 或默认值）。
- `FEISHU_SHEETS_CONFIG` 为新增；`enabled` 默认 False，未配置 `folder_token`/`app_id`/`app_secret` 时不同步。

## Open Questions

- 是否在应用内持久化 `strategy_name -> spreadsheet_token`，以尽量减少“按标题查找”的飞书调用？（建议：首版可做“按 title 创建，若 409/重名则查 folder 子文件取 token”，后续可加映射表或配置。）
