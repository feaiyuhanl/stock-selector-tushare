# Design: 默认执行性能评估与优化

## Context

- **主流程**：`main()` → Token 校验 → 数据新鲜度报告 → 创建策略/执行器 → 选股（单策略或 combined）→ 保存推荐 → 自动复盘 → 飞书同步 → 可选邮件通知。
- **选股核心路径**：`ScoringStrategy.select_top_stocks` / `IndexWeightStrategy.select_top_stocks`：股票池获取 → `ScoringPreloader.preload_all_data`（阶段1 数据准备、阶段2 数据加载、二次重试）→ `calculate_scores_from_preloaded_data`（阶段3 评分）→ 排序取 TOP_N → 保存推荐。
- **外部约束**：Tushare API 有频率与积分限制；默认线程数 `DEFAULT_MAX_WORKERS = 3`（config），避免 OOM 与限频；复盘与飞书由 `AUTO_REVIEW_CONFIG`、`FEISHU_SHEETS_CONFIG` 控制，默认开启。
- **已有文档**：`docs/performance_analysis.md` 已分析线程数、基本面/财务串行、二次重试、K 线批量阈值等，本设计在其基础上补充「默认执行全链路」与「必须/非必须」划分。

## Goals / Non-Goals

- **Goals**：
  - 明确默认执行各阶段耗时归属（必须 vs 非必须）。
  - 定位主要阻塞点与卡点（API 限频、串行请求、全量检查、复盘 K 线查询等）。
  - 给出可实施的优化方案与优先级，部分通过配置/CLI 可关闭或加速非必须步骤。
- **Non-Goals**：
  - 不强制改变默认行为（如不默认关闭复盘/飞书）。
  - 不在此 change 内实现所有优化项；实现范围以 tasks.md 为准，优先文档与低风险可配置项。

## Decisions

### 1. 必须 vs 非必须阶段

- **必须**：Token 校验、股票池获取、选股数据加载（K 线/基本面/财务）、评分计算、保存推荐。无这些步骤则无法得到选股结果。
- **非必须**：数据新鲜度报告（仅用于提示用户缓存概况）、Tushare 连接测试（已可通过 `test_sources=False` 跳过）、二次重试（补全缺失基本面/财务）、自动复盘、飞书同步、邮件通知。关闭或延后不影响「得到 TOP 推荐并落库」。

### 2. 主要阻塞点与卡点

- **阶段2 数据加载**：每只股票在线程内串行调用 `get_stock_fundamental`、`get_stock_financial`，无批量 API；线程数默认 3，总耗时受限于「股票数 × (基本面+财务) 请求时间 / 线程数」及 Tushare 限频。**卡点**：API 限频与单股串行。
- **二次重试**：对缺失基本面/财务的股票逐个重试，且 `time.sleep(0.1)`，重试量大时线性增加耗时。**卡点**：串行 + 固定延迟。
- **数据新鲜度报告**：`print_data_freshness_report` 会对全股票池做 `batch_check_kline_cache_status`、指数权重逐指数查询、`batch_check_fundamental_status`，在选股前执行，全量 I/O/API。**卡点**：与选股重复检查，可省略以缩短首屏时间。
- **自动复盘**：按日期 × 策略 × 股票循环，每条记录可能调用 `get_stock_close_price`、`calculate_daily_scores`（内部多日 K 线），大量 K 线查询。**卡点**：复盘阶段 K 线请求集中。
- **combined 模式**：两策略串行执行（先 fundamental 再 index_weight），总耗时约为两策略耗时之和。**可选优化**：并行执行两策略（需考虑 DB/缓存并发与资源）。

### 3. 优化方向与优先级

| 优先级 | 方向 | 说明 | 风险/注意 |
|--------|------|------|-----------|
| P1 | 数据新鲜度报告可配置跳过 | 新增 `--skip-freshness-report` 或 config 项，选股前不执行 `print_data_freshness_report` | 低；用户少一层缓存概况提示 |
| P2 | 二次重试并行化或限流 | 重试列表用线程池执行，或取消/缩短 sleep，控制并发避免限频 | 中；需控制 Tushare 请求频率 |
| P3 | 默认线程数 | 当前 `DEFAULT_MAX_WORKERS=3`；在内存与限频允许下可由 config 调高，或文档明确推荐范围 | 中；过高易触发限频或 OOM |
| P4 | 复盘/飞书可关闭或延后 | 已由 config 控制；可文档化「关闭后显著缩短时间」；异步化为更大改动，可选 | 低 |
| P5 | combined 两策略并行 | 两策略在不同线程/进程中并行跑，最后合并结果；需处理共享 DB/缓存写入 | 中高；实现与测试成本较大 |

### 4. 实现策略

- **本 change 内**：以文档与可配置项为主。在 `docs/performance_analysis.md` 中写入「默认执行耗时评估」与「优化方案」；如需，新增「跳过数据新鲜度报告」的 config 或 CLI，其余优化作为后续任务列在 tasks 中。
- **不在此 change 内**：基本面/财务批量 API（依赖 Tushare 接口）、复盘/飞书异步化、combined 并行，仅在设计与 tasks 中列为可选后续项。

## Risks / Trade-offs

- **跳过数据新鲜度报告**：用户看不到选股前缓存概况，可能误以为未刷新；可通过文档说明「需查看时去掉该选项」。
- **二次重试并行**：并发过高会触发 Tushare 限频；需保留总 QPS 或 sleep 控制。
- **提高线程数**：在限频不变前提下，适度提高可缩短阶段2 耗时，但过高会增加失败率与重试，需在文档中给出推荐区间（如 3–8）。

## Migration Plan

- 文档更新：直接合并到 `docs/performance_analysis.md`，无兼容性问题。
- 新增配置/CLI：向后兼容，默认不跳过数据新鲜度报告、不改变线程数；用户显式开启才生效。
- 二次重试行为变更：若改为并行，需在发布说明中注明，并建议首次观察限频与失败率。

## Open Questions

- 是否在默认 combined 模式下提供「只跑一个策略」的快捷方式（如环境变量），以缩短单次耗时？
- 复盘是否需要在未来版本中改为「异步任务」或「独立命令」，与选股解耦？
