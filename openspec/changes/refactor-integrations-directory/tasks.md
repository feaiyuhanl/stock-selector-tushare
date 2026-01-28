# Tasks: 重构 integrations 目录结构

## 任务清单

### 1. 目录重命名
- [ ] 将 `integrations/` 目录重命名为 `exports/`
- [ ] 验证目录结构正确

### 2. 更新代码导入
- [ ] 更新 `stock_selector.py` 中的导入语句
  - 位置：第 500 行
  - 修改：`from integrations.feishu_sheets import sync_review_to_feishu` → `from exports.feishu_sheets import sync_review_to_feishu`

### 3. 更新模块初始化文件
- [ ] 更新 `exports/__init__.py`（原 `integrations/__init__.py`）
  - 添加模块说明
  - 导出 `sync_review_to_feishu` 函数

### 4. 验证功能
- [ ] 运行选股流程，验证飞书同步功能正常
- [ ] 运行 `--sync-feishu-only` 参数，验证功能正常
- [ ] 检查日志输出，确认无导入错误

### 5. 更新文档（可选）
- [ ] 更新 `README.md` 中的目录结构说明（如存在）
- [ ] 更新相关文档中的导入示例

## 实施步骤

### Step 1: 重命名目录

```bash
cd d:\py-project\stock-selector-tushare
mv integrations exports
```

### Step 2: 更新导入语句

**文件：`stock_selector.py`**

找到第 500 行：
```python
from integrations.feishu_sheets import sync_review_to_feishu
```

修改为：
```python
from exports.feishu_sheets import sync_review_to_feishu
```

### Step 3: 更新 `__init__.py`

**文件：`exports/__init__.py`**

更新内容为：
```python
"""
数据导出模块 - 将复盘结果导出到外部系统（飞书等）
"""

from .feishu_sheets import sync_review_to_feishu

__all__ = [
    'sync_review_to_feishu',
]
```

### Step 4: 验证

运行以下命令验证功能：

```bash
# 1. 检查导入是否正常
python -c "from exports.feishu_sheets import sync_review_to_feishu; print('导入成功')"

# 2. 运行选股流程（如果配置了飞书）
python stock_selector.py --factor-set combined

# 3. 测试仅同步功能
python stock_selector.py --sync-feishu-only
```

## 回滚方案

如果出现问题，可以快速回滚：

```bash
# 恢复目录名
mv exports integrations

# 恢复导入语句
# 在 stock_selector.py 中将 exports 改回 integrations
```

## 注意事项

1. **确保所有导入已更新**：使用 grep 搜索所有 `integrations` 的引用
   ```bash
   grep -r "integrations" --include="*.py" .
   ```

2. **测试完整流程**：确保选股 → 复盘 → 飞书同步的完整流程正常工作

3. **检查配置文件**：确认 `config.py` 中的 `FEISHU_SHEETS_CONFIG` 配置不受影响
