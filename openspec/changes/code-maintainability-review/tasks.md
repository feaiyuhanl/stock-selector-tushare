# 代码可维护性重构任务清单

## 阶段1：提取公共逻辑（低风险，1-2周）

### 1.1 提取通知发送公共逻辑
- [x] 创建统一的 `_send_notification` 函数
  - [x] 合并 `_send_notification` 和 `_send_combined_notification` 的逻辑
  - [x] 支持单策略和合并策略两种模式
  - [x] 统一防骚扰检查逻辑
  - [x] 统一收件人处理逻辑
- [x] 更新调用处
  - [x] 更新 `main()` 中的调用
  - [ ] 测试单策略模式通知
  - [ ] 测试合并策略模式通知

**文件**：`stock_selector.py`

**预计工作量**：2-3天

---

### 1.2 提取配置验证逻辑
- [x] 创建 `ConfigValidator` 类
  - [x] 实现 `validate_feishu_config` 方法
  - [x] 统一配置检查逻辑
- [x] 更新调用处
  - [x] 更新 `_check_feishu_config` 调用
  - [x] 更新 `_run_feishu_sync` 调用
  - [x] 更新 `_handle_sync_feishu_only` 调用

**文件**：新建 `core/validator.py`，修改 `stock_selector.py`

**预计工作量**：1-2天

---

### 1.3 修复变量作用域问题
- [x] 创建 `_get_current_selector` 辅助函数
- [x] 修复 `main()` 中的异常处理
  - [x] 修复 `KeyboardInterrupt` 处理
  - [x] 修复 `Exception` 处理
- [ ] 测试异常场景
  - [ ] 测试策略创建前异常
  - [ ] 测试策略执行中异常

**文件**：`stock_selector.py`

**预计工作量**：1天

**优先级**：高（可能导致运行时错误）

---

## 阶段2：重构主流程（中风险，2-3周）

### 2.1 创建策略执行器
- [x] 创建 `StrategyExecutor` 类
  - [x] 实现 `execute` 方法（单策略）
  - [x] 实现 `execute_combined` 方法（合并策略）
  - [x] 封装策略创建、执行、保存的完整流程
- [x] 提取策略执行公共逻辑
  - [x] 提取策略创建逻辑
  - [x] 提取参数准备逻辑
  - [x] 提取执行逻辑
  - [x] 提取保存逻辑
- [x] 更新调用处
  - [x] 更新 `main()` 中的调用
  - [ ] 更新 `_handle_sync_feishu_only` 中的调用

**文件**：新建 `core/executor.py`，修改 `stock_selector.py`

**预计工作量**：3-4天

---

### 2.2 创建选股流程管道
- [x] 创建 `SelectionPipeline` 类
  - [x] 实现 `run` 方法（主流程）
  - [x] 实现 `_run_single` 方法（单策略流程）
  - [x] 实现 `_run_combined` 方法（合并策略流程）
  - [x] 实现 `_post_process` 方法（后处理）
  - [x] 实现 `_post_process_combined` 方法（合并策略后处理）
- [x] 实现错误处理
  - [x] 实现 `handle_interrupt` 方法
  - [x] 实现 `handle_error` 方法

**文件**：新建 `core/pipeline.py`，修改 `stock_selector.py`

**预计工作量**：3-4天

---

### 2.3 拆分 main() 函数
- [x] 简化 `main()` 函数
  - [x] 仅保留参数解析和流程编排
  - [x] 移除具体执行逻辑
- [ ] 提取参数解析逻辑
  - [ ] 创建 `_parse_args` 函数（如果不存在）
- [x] 更新异常处理
  - [x] 使用 `SelectionPipeline` 的错误处理方法

**文件**：`stock_selector.py`

**预计工作量**：2-3天

---

### 2.4 统一策略接口
- [x] 更新 `BaseStrategy` 基类
  - [x] 添加 `strategy_type` 属性
  - [x] 统一 `select_top_stocks` 接口签名
  - [x] 支持额外参数（`**kwargs`）
- [x] 更新策略实现
  - [x] 更新 `ScoringStrategy.select_top_stocks`（已支持额外参数）
  - [x] 更新 `IndexWeightStrategy.select_top_stocks`（已支持额外参数）
- [x] 移除外部特殊判断
  - [x] 移除 `_execute_selection` 中的策略类型判断
  - [x] 统一调用策略接口
  - [x] 更新 `_save_recommendations` 使用 `strategy_type` 属性

**文件**：`strategies/base_strategy.py`，`strategies/scoring_strategy.py`，`strategies/index_weight_strategy.py`，`stock_selector.py`

**预计工作量**：2-3天

---

## 阶段3：优化复杂逻辑（高风险，1-2周）

### 3.1 简化复盘逻辑
- [ ] 统一占位记录创建
  - [ ] 创建 `_create_placeholder_review` 方法
  - [ ] 创建 `_create_normal_review` 方法
  - [ ] 创建 `_create_review_record` 统一入口
- [ ] 简化日期处理逻辑
  - [ ] 统一当日/历史日期的处理
  - [ ] 简化 `auto_review_last_n_days` 方法

**文件**：`autoreview/auto_review.py`

**预计工作量**：2-3天

---

### 3.2 优化数据可用性统计
- [ ] 提取数据可用性统计逻辑
  - [ ] 创建 `utils/data_analysis.py`
  - [ ] 实现 `calculate_data_availability` 函数
  - [ ] 实现 `adjust_weights_by_availability` 函数
- [ ] 更新调用处
  - [ ] 更新 `scoring_strategy.py` 中的调用
  - [ ] 更新 `notifications/helpers.py` 中的调用

**文件**：新建 `utils/data_analysis.py`，修改 `strategies/scoring_strategy.py`，`notifications/helpers.py`

**预计工作量**：2-3天

---

### 3.3 改进飞书同步
- [ ] 完善错误处理
  - [ ] 增加详细的错误日志
  - [ ] 统一错误处理策略
- [ ] 添加重试机制
  - [ ] 实现重试逻辑
  - [ ] 配置重试次数和间隔
- [ ] 改进诊断信息
  - [ ] 增加更详细的诊断输出
  - [ ] 改进错误提示信息

**文件**：`stock_selector.py`，`exports/feishu_sheets.py`

**预计工作量**：2-3天

---

## 测试任务

### 单元测试
- [ ] 为 `ConfigValidator` 添加单元测试
- [ ] 为 `StrategyExecutor` 添加单元测试
- [ ] 为 `SelectionPipeline` 添加单元测试
- [ ] 为 `_create_review_record` 添加单元测试
- [ ] 为数据可用性统计函数添加单元测试

### 集成测试
- [ ] 测试单策略完整流程
- [ ] 测试合并策略完整流程
- [ ] 测试 `--sync-feishu-only` 流程
- [ ] 测试异常处理流程

### 回归测试
- [ ] 验证单策略模式功能与重构前一致
- [ ] 验证合并策略模式功能与重构前一致
- [ ] 验证通知功能与重构前一致
- [ ] 验证复盘功能与重构前一致
- [ ] 验证飞书同步功能与重构前一致

### 性能测试
- [ ] 对比重构前后执行时间
- [ ] 对比重构前后内存使用
- [ ] 确保性能不下降

---

## 文档更新

- [ ] 更新 README（如有必要）
- [ ] 更新代码注释
- [ ] 更新架构文档
- [ ] 更新开发指南

---

## 代码Review

- [ ] 阶段1代码review
- [ ] 阶段2代码review
- [ ] 阶段3代码review
- [ ] 最终代码review

---

## 进度跟踪

### 阶段1进度
- 开始日期：_______
- 预计完成日期：_______
- 实际完成日期：_______

### 阶段2进度
- 开始日期：_______
- 预计完成日期：_______
- 实际完成日期：_______

### 阶段3进度
- 开始日期：_______
- 预计完成日期：_______
- 实际完成日期：_______

---

## 风险与问题

### 已知风险
1. **阶段2重构可能影响现有功能**
   - 缓解措施：充分测试，逐步迁移
   
2. **阶段3优化可能引入新bug**
   - 缓解措施：完整测试覆盖，代码review

### 待解决问题
- [ ] 问题1：_______
- [ ] 问题2：_______
- [ ] 问题3：_______

---

## 总结

- **总预计工作量**：15-20个工作日
- **总预计时间**：3-4周（考虑测试和review）
- **优先级**：阶段1 > 阶段2 > 阶段3
