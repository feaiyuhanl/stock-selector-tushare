# Change: 优化复盘功能并支持飞书电子表格同步

## Why

当前复盘逻辑存在以下不足：（1）策略运行后仅对前 N 个交易日做一次复盘，未在每次运行任何策略时统一触发前几个交易日的复盘更新；（2）当日最新推荐结果虽会保存，但未明确强调“每次运行自动更新并记录当日推荐”这一行为；（3）已有复盘结果的日期会重复计算并覆盖，造成无效开销；（4）复盘结果仅存于本地，缺少将结果同步到飞书电子表格的选项，不便于协作与查阅。需要优化复盘流程，并增加通过飞书 Sheets API 同步到飞书表格的能力，一个策略对应一个表格，表格命名规范为 `YYYY_策略_复盘结果`，表不存在时自动创建。

## What Changes

- **MODIFIED**: 每次运行任何策略后，自动更新**前几个交易日**的复盘结果（沿用 `AUTO_REVIEW_CONFIG.review_days`，行为与“前 N 个交易日”一致）。
- **MODIFIED**: 每次运行任何策略后，自动更新并记录**当日**最新推荐结果（复用现有 `_save_recommendations`，选股结果写入 `strategy_recommendations`；若当日已有同策略推荐则按现有逻辑覆盖）。
- **MODIFIED**: 复盘时若某日、某策略、某股票已存在复盘记录，则**跳过**该条，不做重复复盘；仅对缺失或需更新的条目执行复盘计算并写入 `review_summary`。
- **ADDED**: 复盘结果同步开关，支持通过**飞书电子表格（Sheets）API** 将复盘结果同步到飞书表格；一个策略一个飞书电子表格，表格命名：`YYYY_策略_复盘结果`（如 `2026_ScoringStrategy_复盘结果`）；表格列与策略推荐及复盘内容一致；若按名称在指定 `folder_token` 下不存在该表格则自动创建（使用 `POST /open-apis/sheets/v3/spreadsheets`），再通过 Sheets 的 values 接口写入表头与数据。

## Impact

- **Affected specs**: 
  - `review`（新建，复盘行为与推荐记录）
  - `feishu-sheets-sync`（新建，飞书电子表格同步）
- **Affected code**: 
  - `autoreview/auto_review.py`、`autoreview/review_cache.py`、`autoreview/review_helper.py`：复盘触发时机、跳过已有结果、前 N 日 + 当日的语义
  - `stock_selector.py`：策略运行后调用复盘与推荐保存的流程，以及飞书同步开关的调用
  - `config.py`：`AUTO_REVIEW_CONFIG` 扩展；新增 `FEISHU_SHEETS_CONFIG`（含 `enabled`、`folder_token`、`app_id`、`app_secret` 等）
  - 新建 `integrations/feishu_sheets.py`（或 `notifications/feishu_sheets.py`）：飞书 Sheets 创建、按标题查找、values 写入，仅使用 `sheets/v3/spreadsheets` 及 values 相关接口，不使用 `drive/v1/files` 或文档型接口
  - `data/recommendation_cache.py`、`data/cache_base.py`：无 schema 变更；`review_summary`、`strategy_recommendations` 使用方式不变

## 参考

- 飞书创建电子表格：`POST https://open.feishu.cn/open-apis/sheets/v3/spreadsheets`，请求体 `{"title":"xxx","folder_token":"xxx"}`。文档：<https://open.feishu.cn/document/server-docs/docs/sheets-v3/spreadsheet/create>。`folder_token` 格式不要求以 `fld` 开头。
- 所需权限：`drive:drive`（查看、编辑、管理云文档）、`sheets:spreadsheet`（查看、编辑、管理电子表格）、创建电子表格。
