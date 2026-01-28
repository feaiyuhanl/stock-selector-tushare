## MODIFIED Requirements

### Requirement: 复盘结果飞书电子表格同步开关

系统 SHALL 通过 **config** `FEISHU_SHEETS_CONFIG.enabled` 控制是否将复盘结果同步到飞书；仅当该开关为 True 且 `folder_token` 等必填项已配置时，在复盘流程结束后自动按策略同步。**不存在** CLI 指定飞书开关；同步失败不阻塞主流程。

#### Scenario: 开关由 config 控制

- **WHEN** `FEISHU_SHEETS_CONFIG.enabled` 为 True 且 `folder_token` 有效
- **THEN** 复盘完成后自动调用 `_run_feishu_sync`，按策略同步；无需在命令行指定

#### Scenario: 自动补齐飞书表格缺失

- **WHEN** 同步某策略的复盘结果且目标 `folder_token` 下不存在对应标题的电子表格
- **THEN** 先创建表格再写入；若已存在则直接写入全量数据；等价于自动补齐飞书表格缺失
