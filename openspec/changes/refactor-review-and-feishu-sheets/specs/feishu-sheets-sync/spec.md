## ADDED Requirements

### Requirement: 复盘结果飞书电子表格同步开关

系统 SHALL 提供配置开关，控制是否将复盘结果通过飞书 **Sheets API** 同步到飞书电子表格；仅当开关开启且 `folder_token` 等必填项已配置时执行同步；同步失败不阻塞本地复盘与推荐保存。

#### Scenario: 开关关闭时不同步

- **WHEN** `FEISHU_SHEETS_CONFIG.enabled` 为 False 或未配置
- **THEN** 复盘流程结束后不调用任何飞书 API；不请求 `tenant_access_token`、不创建或写入电子表格

#### Scenario: 开关开启且配置完整时按策略同步

- **WHEN** `FEISHU_SHEETS_CONFIG.enabled` 为 True，且 `folder_token`、`app_id`、`app_secret` 均已配置（或从环境变量可获取）
- **THEN** 复盘流程结束后，对本轮涉及的每个 `strategy_name`，从 `ReviewCache.get_review_summary(strategy_name=...)` 获取该策略的复盘 DataFrame；若非空，则调用 `sync_review_to_feishu`，将数据同步到飞书电子表格

#### Scenario: 同步失败不中断主流程

- **WHEN** `sync_review_to_feishu` 调用飞书 API 时发生网络错误、鉴权失败或 4xx/5xx
- **THEN** 记录日志并可选重试 1～2 次；若仍失败，则跳过该次同步，不抛错、不中断选股/复盘/通知流程；本地 `review_summary` 与 `strategy_recommendations` 不受影响

---

### Requirement: 一个策略一个飞书电子表格与命名规范

系统 SHALL 为每个策略单独使用一个飞书电子表格；表格命名格式为 `YYYY_<StrategyName>_复盘结果`，其中 `YYYY` 为当前年份（如 2026），`StrategyName` 为 `strategy.get_strategy_name()`（如 `ScoringStrategy`、`IndexWeightStrategy`）；表格不存在时自动创建。

#### Scenario: 按命名创建新表格

- **WHEN** 同步某策略的复盘结果，且目标 `folder_token` 下不存在标题为 `{YYYY}_{StrategyName}_复盘结果` 的电子表格
- **THEN** 系统调用 `POST https://open.feishu.cn/open-apis/sheets/v3/spreadsheets`，Body `{"title":"{YYYY}_{StrategyName}_复盘结果","folder_token":"<folder_token>"}`；使用返回的 `spreadsheet_token` 执行后续 values 写入；**不使用** `drive/v1/files` 创建

#### Scenario: 表格已存在时只写入不创建

- **WHEN** 通过“按标题查找”或应用内维护的 `strategy_name -> spreadsheet_token` 映射，得到已存在的 `spreadsheet_token`
- **THEN** 不再调用创建接口；直接使用该 `spreadsheet_token` 调用 values 写入接口，将本次复盘数据（表头+行）写入

#### Scenario: folder_token 格式

- **WHEN** 调用创建接口或按文件夹查找子文件
- **THEN** `folder_token` 支持飞书 API 所接受的格式；不要求必须以 `fld` 开头（例如 `PKOufdBLI1U9PSdiRcWcwLoSnne` 等格式均可用）

---

### Requirement: 表格列与策略结果及复盘内容一致

写入飞书电子表格的列 SHALL 与“策略结果和复盘内容保持一致”；即表头与数据列与 `review_summary` 的导出列或 `get_review_summary` 返回的 DataFrame 列一致（或与策略推荐关键字段 + 复盘字段的约定子集一致），使表格内容与本地复盘报告、`review_summary` 可对应。

#### Scenario: 表头与 review_summary 列对应

- **WHEN** 调用 `write_review_to_sheet(spreadsheet_token, df)` 写入飞书表格
- **THEN** `df` 的列名作为表头第一行写入；列顺序与 `ReviewCache.get_review_summary` 返回的 DataFrame 列顺序一致（或与 `review_summary` 表字段对应：如 `recommendation_date`、`strategy_name`、`stock_code`、`stock_name`、`recommendation_price`、`rank`、`day1_price`、`day1_score` … `day10_price`、`day10_score`、`average_score`、`total_score`、`valid_days`、`last_update_time`）；策略特有字段（如 `category`）若存在于复盘导出中则一并写入

#### Scenario: 与本地复盘报告可对应

- **WHEN** 用户查看飞书表格中的某策略复盘数据
- **THEN** 列名与含义与本地 `review_helper.generate_review_report` 或 `get_review_summary` 的字段可对应，便于与本地复盘结果对照

---

### Requirement: 使用飞书 Sheets API 创建与写入

创建电子表格 SHALL 仅使用 `POST /open-apis/sheets/v3/spreadsheets`；写入单元格 SHALL 使用飞书 Sheets 的 **values 写入接口**（如 `PUT /open-apis/sheets/v2/spreadsheets/{spreadsheetToken}/values/{range}` 或 v3 等价接口）。不得使用 `drive/v1/files`、文档、多维表格等非 Sheets 接口创建或存储复盘结果。

#### Scenario: 仅用 sheets/v3 创建

- **WHEN** 需要新建飞书电子表格
- **THEN** 请求 `POST https://open.feishu.cn/open-apis/sheets/v3/spreadsheets`，Body 含 `title`、`folder_token`；不使用 `POST https://open.feishu.cn/open-apis/drive/v1/files` 或其它 drive 创建文件接口

#### Scenario: 使用 values 接口写入

- **WHEN** 将复盘表头与数据写入已存在的电子表格
- **THEN** 使用飞书 Sheets 的 values 范围写入接口，将二维数组（表头+数据行）写入指定 `range`（如首 sheet 的 `A1:Z{n}`）；鉴权使用 `tenant_access_token`（通过 `app_id`、`app_secret` 获取）

#### Scenario: 应用权限

- **WHEN** 配置飞书应用以支持创建与写入电子表格
- **THEN** 应用需具备：查看、评论、编辑和管理云空间中所有文件（`drive:drive`）；查看、评论、编辑和管理电子表格（`sheets:spreadsheet`）；创建电子表格；`folder_token` 对应文件夹需在应用可访问范围内
