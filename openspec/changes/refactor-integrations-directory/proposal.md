# Change: 重构 integrations 目录结构

## Why

当前 `integrations/` 目录存在以下问题：

1. **目录层次过深**：只有一个文件 `feishu_sheets.py`，单独创建一个目录显得冗余
2. **命名过于泛化**：`integrations` 可以包含任何第三方集成，不够具体
3. **功能定位不清晰**：
   - `notifications/` 目录：实时通知（邮件、微信），用于选股结果推送
   - `integrations/` 目录：数据同步/导出（飞书），用于复盘结果持久化
   - 两者功能不同但命名风格不一致
4. **与项目整体风格不符**：其他模块都是功能导向命名（`strategies/`、`scorers/`、`notifications/`），而 `integrations/` 是技术导向命名

## Current Structure

```
stock-selector-tushare/
├── integrations/          # 第三方集成（仅飞书）
│   ├── __init__.py
│   └── feishu_sheets.py   # 飞书电子表格同步（复盘结果）
├── notifications/         # 通知模块（邮件、微信）
│   ├── __init__.py
│   ├── base.py
│   ├── email_notifier.py
│   └── wechat.py
├── autoreview/            # 自动复盘模块
├── data/                  # 数据模块
├── strategies/            # 策略模块
└── scorers/               # 评分模块
```

## Analysis

### 功能分析

**`integrations/feishu_sheets.py` 的功能**：
- 同步复盘结果到飞书电子表格
- 创建/查找电子表格
- 写入数据到工作表
- 属于**数据导出/同步**功能，而非通知功能

**使用位置**：
- `stock_selector.py:500` - 仅在 `_run_feishu_sync` 函数中导入使用
- 调用路径：选股 → 复盘 → 飞书同步（由 `FEISHU_SHEETS_CONFIG.enabled` 控制）

### 与 notifications 的区别

| 维度 | notifications | integrations |
|------|--------------|--------------|
| **功能** | 实时通知（推送） | 数据同步（持久化） |
| **触发时机** | 选股完成后立即发送 | 复盘完成后同步 |
| **数据内容** | 选股结果（推荐列表） | 复盘结果（表现分析） |
| **使用场景** | 主动推送，提醒用户 | 被动同步，数据归档 |
| **架构模式** | 工厂模式（BaseNotifier） | 函数式（直接调用） |

## Proposed Solutions

### 方案1：重命名为 `exports/` 或 `outputs/` ⭐ 推荐

**优点**：
- 命名清晰，明确表示数据导出功能
- 与 `notifications/` 形成对比（通知 vs 导出）
- 未来可扩展其他导出方式（Excel、CSV、数据库等）

**缺点**：
- 如果未来有其他类型的集成（非导出类），命名可能不够准确

**目录结构**：
```
stock-selector-tushare/
├── exports/               # 数据导出模块
│   ├── __init__.py
│   └── feishu_sheets.py
```

### 方案2：重命名为 `sync/` 或 `syncs/`

**优点**：
- 明确表示同步功能
- 简洁明了

**缺点**：
- 如果未来有非同步类的集成，命名不够准确

### 方案3：合并到 `notifications/` 作为子模块

**优点**：
- 减少目录层级
- 统一外部服务管理

**缺点**：
- **不推荐**：功能定位不同（通知 vs 数据同步），合并会混淆概念
- 破坏单一职责原则

### 方案4：重命名为 `feishu/` 并扁平化

**优点**：
- 具体明确，直接表明是飞书相关功能
- 如果未来有更多飞书功能（如飞书通知、飞书文档等），可以扩展

**缺点**：
- 如果未来有其他第三方服务（非飞书），需要再创建新目录

**目录结构**：
```
stock-selector-tushare/
├── feishu/                # 飞书集成模块
│   ├── __init__.py
│   └── sheets.py          # 重命名：feishu_sheets.py → sheets.py
```

### 方案5：直接放在根目录或 `utils/` 下

**优点**：
- 最简单，减少目录层级

**缺点**：
- 破坏模块化结构
- 与项目整体架构风格不符

## Recommendation

**推荐方案1：重命名为 `exports/`**

**理由**：
1. **功能定位准确**：飞书同步本质是数据导出/持久化，而非通知
2. **命名清晰**：`exports/` 明确表示导出功能，与 `notifications/`（通知）形成清晰对比
3. **扩展性好**：未来可添加其他导出方式（如 `exports/excel.py`、`exports/csv.py`）
4. **风格一致**：与项目其他功能导向命名保持一致

## Implementation Plan

### Step 1: 重命名目录和文件

```bash
# 重命名目录
mv integrations exports

# 可选：重命名文件（保持 feishu_sheets.py 或改为 sheets.py）
# 建议保持 feishu_sheets.py，因为未来可能有其他飞书功能（如 feishu_docs.py）
```

### Step 2: 更新导入语句

**文件：`stock_selector.py`**
```python
# 修改前
from integrations.feishu_sheets import sync_review_to_feishu

# 修改后
from exports.feishu_sheets import sync_review_to_feishu
```

### Step 3: 更新 `__init__.py`

**文件：`exports/__init__.py`**
```python
"""
数据导出模块 - 将复盘结果导出到外部系统（飞书等）
"""

from .feishu_sheets import sync_review_to_feishu

__all__ = [
    'sync_review_to_feishu',
]
```

### Step 4: 更新文档

- 更新 `README.md` 中的目录结构说明
- 更新相关文档中的导入示例

## Impact

- **Affected files**:
  - `stock_selector.py:500` - 更新导入语句
  - `integrations/` → `exports/` - 目录重命名
  - `integrations/__init__.py` → `exports/__init__.py` - 更新内容
  - `README.md` - 更新目录结构说明（如存在）

- **Breaking changes**: 
  - 无（如果正确更新所有导入语句）

- **Backward compatibility**:
  - 需要更新所有导入语句，否则会破坏兼容性

## Alternative: 如果选择方案4（feishu/）

如果选择方案4，实现步骤类似，但：
- 目录名：`integrations/` → `feishu/`
- 文件名：`feishu_sheets.py` → `sheets.py`（可选，保持原名也可）
- 导入：`from feishu.sheets import sync_review_to_feishu` 或 `from feishu.feishu_sheets import sync_review_to_feishu`

## Future Considerations

如果未来需要添加其他导出方式，`exports/` 目录结构：

```
exports/
├── __init__.py
├── feishu_sheets.py      # 飞书电子表格
├── excel.py              # Excel 导出（可选）
└── csv.py                # CSV 导出（可选）
```

如果选择方案4（`feishu/`），未来结构：

```
feishu/
├── __init__.py
├── sheets.py             # 电子表格同步
├── docs.py               # 文档同步（可选）
└── notification.py      # 飞书通知（可选，与 notifications/ 区分）
```
