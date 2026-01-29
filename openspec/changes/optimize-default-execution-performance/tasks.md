## 1. 文档：默认执行耗时评估与优化方案

- [x] 1.1 在 `docs/performance_analysis.md` 中新增或重写「默认执行流程耗时阶段」小节：列出启动 → 数据新鲜度检查 → 选股数据加载 → 评分计算 → 复盘 → 飞书同步 → 通知，并注明每阶段主要耗时来源。
- [x] 1.2 在同一文档中新增「必须 vs 非必须」小节：界定必须步骤（Token 校验、股票池、数据加载与评分、保存推荐）与非必须步骤（数据新鲜度报告、二次重试、复盘、飞书、通知），并说明非必须步骤关闭或延后对结果的影响。
- [x] 1.3 在同一文档中新增「主要阻塞点与卡点」小节：说明阶段2 数据加载（API 限频与单股串行）、二次重试（串行 + sleep）、数据新鲜度报告（全量检查）、复盘（大量 K 线查询）、combined 串行执行等卡点。
- [x] 1.4 在同一文档中新增「优化方案与优先级」小节：列出可配置跳过数据新鲜度报告、二次重试并行/限流、默认线程数配置、复盘/飞书可关闭、combined 并行（可选）等，并标注优先级与风险/注意点。

## 2. 可选：数据新鲜度报告可配置跳过

- [x] 2.1 在 `config.py` 或 CLI 中新增「跳过数据新鲜度报告」选项（如 `SKIP_FRESHNESS_REPORT` 或 `--skip-freshness-report`），默认 False。
- [x] 2.2 在 `stock_selector.py` 主流程中，若该选项为 True，则选股前不调用 `print_data_freshness_report`；否则保持现有行为。
- [x] 2.3 在 `docs/performance_analysis.md` 或配置说明中注明该选项的用途与对耗时的影响。

## 3. 可选：二次重试并行化或限流

- [x] 3.1 在 `strategies/scoring_preloader.py` 中，将二次重试由「逐个请求 + sleep(0.1)」改为使用线程池并行重试（控制 max_workers，如 2–3），或取消/缩短 sleep 并保留限频逻辑。
- [x] 3.2 确保重试阶段不显著增加 Tushare 限频风险（总 QPS 或间隔可控）。
- [x] 3.3 在文档中说明二次重试行为变更及推荐配置。

## 4. 可选：默认线程数与批量阈值

- [x] 4.1 确认 `config.DEFAULT_MAX_WORKERS` 与 `scoring_preloader`、`scoring_strategy` 中 max_workers 传递一致，无硬编码覆盖（参考现有 `docs/performance_analysis.md` 线程数问题）。
- [x] 4.2 在 `docs/performance_analysis.md` 中给出默认线程数推荐范围（如 3–8）及与 Tushare 限频、内存的权衡说明。
- [x] 4.3 （可选）降低 K 线批量加载阈值（当前 ≥50 只才走批量），或文档说明小股票池的耗时差异。

## 5. 校验

- [ ] 5.1 运行 `openspec validate optimize-default-execution-performance --strict --no-interactive` 通过。
- [x] 5.2 确认文档与代码改动（若有）符合 proposal 与 design 中的范围与优先级。
