# A股选股程序 - Tushare版本

基于Python3和tushare的A股选股程序，采用多维度打分策略进行股票筛选。支持本地缓存机制、数据预加载、多线程处理，大幅提升运行速度。

## 功能特点

- **多维度评分**：综合考虑基本面、成交量、成交价格、关联板块走势、关联概念走势等维度
- **子维度细化**：每个大维度下包含多个子维度，评分更加精准
- **权重可配置**：支持自定义各维度权重，灵活调整选股策略
- **TOP结果输出**：自动筛选并输出评分最高的股票
- **本地缓存机制**：低频数据（基本面、财务、板块概念）自动缓存到本地Excel，大幅提升运行速度
- **数据预加载**：支持提前批量获取并缓存数据，首次运行后速度提升10-100倍
- **多线程支持**：使用多线程并行处理，大幅提升处理速度
- **板块筛选**：支持按板块类型筛选（主板、创业板、科创板、北交所、B股），默认只选主板
- **策略扩展性**：采用策略模式，便于扩展新的选股策略
- **缓存控制**：支持强制刷新缓存，确保数据最新
- **稳定数据源**：基于tushare，提供稳定的数据源，避免限流问题

## 项目结构

```
stock-selector-tushare/
├── config.py                 # 配置文件（权重、参数等）
├── stock_selector.py         # 主程序（支持多策略）
├── requirements.txt          # 依赖包
├── README.md                 # 说明文档（本文件）
│
├── data/                     # 数据模块
│   ├── __init__.py
│   ├── cache_manager.py      # 缓存管理模块
│   └── fetcher.py            # 数据获取模块（基于tushare）
│
├── strategies/               # 策略模块
│   ├── __init__.py
│   ├── base_strategy.py      # 基础策略类
│   └── scoring_strategy.py   # 打分策略（当前策略）
│
├── scorers/                  # 评分模块目录
│   ├── __init__.py
│   ├── fundamental_scorer.py   # 基本面评分
│   ├── volume_scorer.py        # 成交量评分
│   ├── price_scorer.py         # 价格评分
│   ├── sector_scorer.py        # 板块走势评分
│   └── concept_scorer.py        # 概念走势评分
│
└── cache/                    # 缓存目录（自动创建）
    ├── data/                  # 数据文件目录（按类型分类，每个股票独立文件）
    │   ├── kline/            # K线数据
    │   ├── fundamental/      # 基本面数据
    │   ├── financial/        # 财务数据
    │   ├── sectors/          # 板块数据
    │   └── concepts/          # 概念数据
    └── meta/                  # 元数据目录（集中存储文件）
        ├── fundamental_data.xlsx
        ├── financial_data.xlsx
        ├── stock_sectors.xlsx
        ├── stock_concepts.xlsx
        └── stock_list.xlsx
```

## 安装依赖

### 1. 安装Python包

```bash
pip install -r requirements.txt
```

### 2. 配置Tushare Token

**重要**：使用本程序前，必须先配置tushare token。

#### 第一步：获取Token

1. **注册账号**：访问 [Tushare官网](https://tushare.pro/register) 注册账号
2. **获取Token**：登录后，进入"接口"页面，复制您的Token
3. **了解积分限制**：Tushare采用积分制度管理API访问权限，不同积分等级对应不同的调用限制和接口权限

#### 第二步：配置Token（三种方式任选一种）

程序支持三种方式配置Token，按优先级从高到低：

##### 方式1：环境变量（推荐）⭐

这是最推荐的方式，因为不会将敏感信息提交到代码仓库，可以在不同环境使用不同的Token。

**Windows PowerShell**：
```powershell
# 临时设置（当前会话有效）
$env:TUSHARE_TOKEN="your_token_here"

# 永久设置（用户级别）
[System.Environment]::SetEnvironmentVariable("TUSHARE_TOKEN", "your_token_here", "User")
```

**Windows CMD**：
```cmd
# 临时设置（当前会话有效，关闭CMD窗口后失效）
set TUSHARE_TOKEN=your_token_here

# 永久设置（用户级别，重启CMD后生效）
setx TUSHARE_TOKEN "your_token_here"

# 永久设置（系统级别，需要管理员权限，所有用户可用）
setx TUSHARE_TOKEN "your_token_here" /M
```

**注意**：
- `set` 命令：临时设置，只在当前CMD窗口有效，关闭窗口后失效
- `setx` 命令：永久设置，但需要重新打开CMD窗口才能生效（不会影响当前窗口）
- 如果使用 `setx`，设置后需要关闭并重新打开CMD窗口才能使用新环境变量
- 使用 `/M` 参数需要管理员权限，设置后所有用户都可以使用

**Linux/Mac**：
```bash
# 临时设置（当前会话有效）
export TUSHARE_TOKEN="your_token_here"

# 永久设置（添加到 ~/.bashrc 或 ~/.zshrc）
echo 'export TUSHARE_TOKEN="your_token_here"' >> ~/.bashrc
source ~/.bashrc
```

**验证环境变量**：
```bash
# Windows PowerShell
echo $env:TUSHARE_TOKEN

# Windows CMD
echo %TUSHARE_TOKEN%

# Linux/Mac
echo $TUSHARE_TOKEN
```

**Windows CMD 设置环境变量详细说明**：

1. **临时设置（推荐用于测试）**：
   ```cmd
   set TUSHARE_TOKEN=your_token_here
   ```
   - 只在当前CMD窗口有效
   - 关闭窗口后失效
   - 立即生效，无需重启

2. **永久设置（用户级别）**：
   ```cmd
   setx TUSHARE_TOKEN "your_token_here"
   ```
   - 永久保存到用户环境变量
   - 需要重新打开CMD窗口才能生效
   - 只对当前用户有效

3. **永久设置（系统级别）**：
   ```cmd
   setx TUSHARE_TOKEN "your_token_here" /M
   ```
   - 需要以管理员身份运行CMD
   - 永久保存到系统环境变量
   - 所有用户都可以使用
   - 需要重新打开CMD窗口才能生效

4. **查看环境变量**：
   ```cmd
   # 查看单个环境变量
   echo %TUSHARE_TOKEN%
   
   # 查看所有环境变量
   set
   
   # 查看所有以TUSHARE开头的环境变量
   set TUSHARE
   ```

5. **删除环境变量**：
   ```cmd
   # 删除用户级别环境变量（需要重启CMD）
   reg delete "HKCU\Environment" /v TUSHARE_TOKEN /f
   
   # 删除系统级别环境变量（需要管理员权限）
   reg delete "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v TUSHARE_TOKEN /f
   ```

**推荐做法**：
- 测试时使用 `set` 命令（临时设置）
- 正式使用时使用 `setx` 命令（永久设置）
- 设置后记得重新打开CMD窗口

##### 方式2：配置文件

编辑 `config.py` 文件，找到以下行：

```python
# Tushare配置
TUSHARE_TOKEN = None  # 需要在环境变量或配置文件中设置，或通过代码设置
```

修改为：

```python
# Tushare配置
TUSHARE_TOKEN = "your_token_here"  # 替换为您的实际Token
```

**注意**：⚠️ 不要将包含Token的config.py提交到Git仓库

##### 方式3：代码中设置

在运行程序前，在代码中设置：

```python
import tushare as ts
ts.set_token('your_token_here')
```

#### 第三步：验证配置

运行测试脚本验证Token配置：

```bash
python test_token.py
```

如果看到 "✅ Token配置验证通过！" 表示配置成功。

也可以运行示例程序：

```bash
python example.py
```

如果配置正确，程序会正常运行；如果配置错误，会显示相应的错误信息。

### Tushare积分等级与API接口差异

Tushare采用积分制度来管理用户对不同API接口的访问权限。不同积分等级对应不同的API调用频次和可访问的接口范围。

#### 积分等级对照表

| 积分数 | 每分钟调用次数 | 每日总调用次数上限 | 可访问的接口范围 | 捐助金额（元） |
|--------|---------------|-------------------|-----------------|---------------|
| **120** | 50 | 8,000 | 股票基础信息、股票非复权日线行情，其他接口无法调用 | 0（免费） |
| **2000以上** | 200 | 每个API每日100,000次 | Tushare Pro 60%的API可调用，具体参考每个接口的积分要求 | 200 |
| **5000以上** | 500 | 常规数据无上限 | Tushare Pro 90%的API可调用，具体参考每个接口的积分要求 | 500 |
| **10000以上** | 1,000 | 常规数据无上限，特色数据每分钟300次 | 包括盈利预测数据、每日筹码和胜率、筹码分布、券商每月金股等特色数据权限 | 1,000 |
| **15000以上** | 1,000 | 特色数据无总量限制 | 特色数据专属权限 | 1,500 |

#### 本程序使用的API接口及积分要求

本程序主要使用以下Tushare API接口：

| API接口 | 用途 | 最低积分要求 | 说明 |
|---------|------|-------------|------|
| `stock_basic` | 获取股票列表 | 120 | 免费用户可用 |
| `daily` | 获取日K线数据 | 120 | 免费用户可用 |
| `daily_basic` | 获取每日指标（PE、PB、换手率等） | 120 | 免费用户可用 |
| `fina_indicator` | 获取财务指标（ROE等） | 2000 | 需要2000积分以上 |
| `income` | 获取利润表数据 | 2000 | 需要2000积分以上 |
| `index_basic` | 获取指数基本信息 | 2000 | 用于板块K线（待实现） |
| `index_daily` | 获取指数日线行情 | 2000 | 用于板块K线（待实现） |

#### 评分器数据支持情况

| 评分器 | 数据支持情况 | 免费用户（120积分） | 付费用户（2000积分） | 说明 |
|--------|------------|-------------------|---------------------|------|
| **PriceScorer** | ✅ 完全支持 | ✅ 完全可用 | ✅ 完全可用 | 价格数据完整 |
| **VolumeScorer** | ✅ 完全支持 | ✅ 完全可用 | ✅ 完全可用 | 已优化换手率获取 |
| **FundamentalScorer** | ⚠️ 部分支持 | ⚠️ 部分可用（仅PE、PB） | ✅ 完全可用 | ROE、增长率需付费 |
| **SectorScorer** | ✅ 已实现 | ❌ 不可用（需2000积分） | ✅ 完全可用 | 通过行业指数获取 |
| **ConceptScorer** | ✅ 已实现 | ❌ 不可用（需2000积分） | ✅ 完全可用 | 通过概念成分股计算 |

#### 评分器数据需求与Tushare接口对应表

##### 1. FundamentalScorer（基本面评分器）

| 数据项 | 用途 | Tushare接口 | 积分要求 | 实现状态 |
|--------|------|------------|---------|---------|
| `pe_ratio` (市盈率) | 市盈率评分 | `daily_basic` | 120 | ✅ 已实现 |
| `pb_ratio` (市净率) | 市净率评分 | `daily_basic` | 120 | ✅ 已实现 |
| `roe` (净资产收益率) | ROE评分 | `fina_indicator` | 2000 | ✅ 已实现 |
| `revenue_growth` (营收增长率) | 营收增长率评分 | `income` (计算) | 2000 | ✅ 已实现 |
| `profit_growth` (利润增长率) | 利润增长率评分 | `income` (计算) | 2000 | ✅ 已实现 |

**实现位置**：`data/fetcher.py::get_stock_fundamental()`, `get_stock_financial()`

##### 2. VolumeScorer（成交量评分器）

| 数据项 | 用途 | Tushare接口 | 积分要求 | 实现状态 |
|--------|------|------------|---------|---------|
| `volume` (成交量) | 量比、成交量趋势 | `daily` | 120 | ✅ 已实现 |
| `turnover_rate` (换手率) | 换手率评分 | `daily_basic` | 120 | ✅ 已优化 |

**实现位置**：`data/fetcher.py::get_stock_kline()`（已优化，同时获取换手率）

##### 3. PriceScorer（价格评分器）

| 数据项 | 用途 | Tushare接口 | 积分要求 | 实现状态 |
|--------|------|------------|---------|---------|
| `close` (收盘价) | 价格趋势、位置、波动率 | `daily` | 120 | ✅ 已实现 |
| `open`, `high`, `low` | 辅助计算 | `daily` | 120 | ✅ 已实现 |

**实现位置**：`data/fetcher.py::get_stock_kline()`

##### 4. SectorScorer（板块走势评分器）

| 数据项 | 用途 | Tushare接口 | 积分要求 | 实现状态 |
|--------|------|------------|---------|---------|
| `sector_kline` (板块K线) | 板块趋势、相对强度 | `index_basic` + `index_daily` | 2000 | ✅ 已实现 |
| `stock_kline` (股票K线) | 对比用 | `daily` | 120 | ✅ 已实现 |

**实现位置**：`data/fetcher.py::get_sector_kline()`（通过行业指数获取）

##### 5. ConceptScorer（概念走势评分器）

| 数据项 | 用途 | Tushare接口 | 积分要求 | 实现状态 |
|--------|------|------------|---------|---------|
| `concept_kline` (概念K线) | 概念趋势、相对强度 | `concept_detail` + `daily` (计算) | 2000 | ✅ 已实现 |
| `stock_kline` (股票K线) | 对比用 | `daily` | 120 | ✅ 已实现 |

**实现位置**：`data/fetcher.py::get_concept_kline()`（通过概念成分股计算概念指数）

#### 所有使用的Tushare接口汇总

| Tushare接口 | 用途 | 积分要求 | 调用位置 |
|------------|------|---------|---------|
| `stock_basic` | 获取股票列表、行业信息 | 120 | `get_stock_list()`, `get_stock_sectors()` |
| `daily` | 获取日K线数据（价格、成交量） | 120 | `get_stock_kline()`, `get_concept_kline()` |
| `daily_basic` | 获取每日指标（PE、PB、换手率） | 120 | `get_stock_kline()`, `get_stock_fundamental()` |
| `fina_indicator` | 获取财务指标（ROE等） | 2000 | `get_stock_financial()` |
| `income` | 获取利润表数据（计算增长率） | 2000 | `get_stock_financial()` |
| `index_basic` | 获取指数基本信息（行业指数列表） | 2000 | `get_sector_kline()` |
| `index_daily` | 获取指数日线行情（行业指数K线） | 2000 | `get_sector_kline()` |
| `concept_detail` | 获取概念成分股列表 | 2000 | `get_stock_concepts()`, `get_concept_kline()` |

**接口文档**：
- [daily - 日线行情](https://tushare.pro/document/2?doc_id=27)
- [daily_basic - 每日指标](https://tushare.pro/document/2?doc_id=32)
- [fina_indicator - 财务指标](https://tushare.pro/document/2?doc_id=95)
- [income - 利润表](https://tushare.pro/document/2?doc_id=36)
- [index_basic - 指数基本信息](https://tushare.pro/document/2?doc_id=94)
- [index_daily - 指数日线行情](https://tushare.pro/document/2?doc_id=94)
- [concept_detail - 概念股分类](https://tushare.pro/document/2?doc_id=126)

#### 积分等级建议

- **免费用户（120积分）**：
  - ✅ 可以使用价格评分、成交量评分（含换手率）
  - ✅ 可以使用基本面评分（PE、PB）
  - ⚠️ 无法获取财务数据（ROE、增长率等），财务评分维度会使用默认值
  - ❌ 无法使用板块评分和概念评分（需要2000积分）
  - ⚠️ 每日调用次数限制为8,000次，适合少量股票分析

- **2000积分用户（推荐）**：
  - ✅ 可以使用本程序的所有功能
  - ✅ 可以获取完整的财务数据（ROE、增长率）
  - ✅ 可以使用板块评分和概念评分
  - ✅ 每日调用次数大幅提升（每个API 100,000次）
  - 💰 需要充值200元

- **5000积分及以上**：
  - ✅ 适合大规模批量分析
  - ✅ 常规数据无调用上限
  - ✅ 可以访问更多高级接口

#### 如何查看和提升积分

1. **查看当前积分**：登录 [Tushare官网](https://tushare.pro/)，在"积分"页面查看
2. **提升积分**：
   - 免费用户：完成网站任务、邀请好友等方式获得积分
   - 付费用户：充值获得积分（1元=10积分）
3. **查看接口积分要求**：每个API接口的文档页面会显示所需的最低积分

#### 积分不足时的处理

如果遇到"积分不足"的错误：

1. **检查当前积分**：登录官网查看剩余积分
2. **优化调用频率**：
   - 减少并发线程数（`--workers` 参数）
   - 充分利用缓存机制，避免重复请求
   - 分批处理股票，避免一次性请求过多
3. **升级积分**：如果频繁使用，建议充值获取更多积分

**注意**：具体的积分要求和接口权限可能会随着时间有所调整，建议访问 [Tushare官方网站](https://tushare.pro/) 或其官方文档以获取最新信息。

## 快速开始

### 推荐流程（首次使用）

程序首次运行时会自动检查缓存完整性，如果覆盖率不足会自动预加载数据。你也可以直接运行选股程序，程序会自动处理数据加载：

```bash
# 运行选股程序（首次运行会自动预加载数据）
python stock_selector.py --board main
```

**注意**：首次运行可能需要较长时间下载数据，建议在网络良好的环境下运行。后续运行会使用缓存数据，速度会快很多。

### 基本使用

```bash
# 直接运行主程序
python stock_selector.py
```

## 命令行参数

### 主程序参数

```bash
python stock_selector.py --help
```

主要参数：

- `--refresh`: 强制刷新缓存
- `--strategy`: 选股策略（当前仅支持scoring）
- `--top-n`: 返回前N只股票（默认20）
- `--stocks`: 指定股票代码列表（如：`--stocks 000001 000002`）
- `--board`: 板块类型（main/sme/gem/star/bse/b），可多选（如：`--board main gem`）
- `--workers`: 线程数（默认10）

### 使用示例

```bash
# 选择主板前10只股票
python stock_selector.py --board main --top-n 10

# 评估指定股票
python stock_selector.py --stocks 000001 000002 600000

# 选择主板和创业板股票
python stock_selector.py --board main gem --top-n 30

# 强制刷新缓存
python stock_selector.py --refresh --board main
```

## 配置说明

### 权重配置

编辑 `config.py` 文件可以调整各维度权重：

```python
# 各维度权重配置（总和应为1.0）
WEIGHT_CONFIG = {
    'fundamental': 0.30,      # 基本面权重
    'volume': 0.20,           # 成交量权重
    'price': 0.20,            # 成交价格权重
    'sector': 0.15,           # 关联板块走势权重
    'concept': 0.15,          # 关联概念走势权重
}
```

### 板块类型配置

```python
# 默认板块筛选（只选主板）
DEFAULT_BOARD_TYPES = ['main']  # 可以修改为 ['main', 'gem'] 等
```

## 与Akshare版本的区别

1. **数据源**：使用tushare替代akshare，提供更稳定的数据源
2. **Token配置**：需要配置tushare token才能使用
3. **API调用**：使用tushare的API接口，调用方式略有不同
4. **数据格式**：数据格式基本一致，但部分字段名称可能略有差异
5. **限流处理**：tushare有积分限制，但不会像akshare那样频繁限流

## 注意事项

1. **Token配置**：必须配置有效的tushare token才能使用
2. **积分限制**：
   - 免费用户（120积分）只能使用基础功能，无法获取财务数据
   - 建议至少充值到2000积分以使用完整功能
   - 注意每日调用次数限制，合理使用缓存机制
3. **数据延迟**：部分数据可能有延迟，建议在收盘后使用
4. **缓存管理**：首次运行会下载数据，后续运行会使用缓存，速度更快
5. **板块/概念数据**：当前版本对板块和概念的K线数据获取做了简化处理，可能返回空数据
6. **API调用频率**：注意tushare的调用频率限制，避免触发限流

## 常见问题

### Token配置相关问题

#### Q1: 提示"未设置Tushare Token"怎么办？

**原因**：程序找不到Token配置

**解决方法**：
1. 检查是否设置了环境变量：`echo $TUSHARE_TOKEN`（Linux/Mac）或 `echo %TUSHARE_TOKEN%`（Windows CMD）
2. 检查config.py中是否设置了TUSHARE_TOKEN
3. 确保Token字符串正确（没有多余的空格或引号）
4. 运行 `python test_token.py` 进行诊断

#### Q2: 提示"权限不足"或"积分不足"怎么办？

**原因**：Token有效，但积分不足或积分等级不够

**解决方法**：
1. 登录 [Tushare官网](https://tushare.pro/)
2. 查看"积分"页面，检查剩余积分和积分等级
3. **免费用户（120积分）**：
   - 只能使用基础功能（股票列表、K线、基本面数据）
   - 无法获取财务数据，财务评分会使用默认值
   - 每日调用次数限制为8,000次
4. **需要完整功能**：
   - 建议充值到2000积分以上（200元）
   - 可以获取完整的财务数据
   - 每日调用次数大幅提升
5. **查看具体接口要求**：每个API接口的文档会显示所需的最低积分

#### Q3: 提示"Token无效"怎么办？

**原因**：Token字符串错误或已过期

**解决方法**：
1. 重新登录Tushare官网，复制最新的Token
2. 确保Token字符串完整（没有截断）
3. 确保没有多余的空格或特殊字符
4. 重新配置Token并运行 `python test_token.py` 验证

#### Q4: 如何在不同项目中使用不同的Token？

**推荐方式**：使用环境变量，在不同项目的启动脚本中设置不同的Token

**示例**：
```bash
# 项目1的启动脚本 start_project1.sh
export TUSHARE_TOKEN="token_for_project1"
python stock_selector.py

# 项目2的启动脚本 start_project2.sh
export TUSHARE_TOKEN="token_for_project2"
python stock_selector.py
```

#### Q5: 如何安全地管理Token？

**最佳实践**：
1. ✅ 使用环境变量存储Token（不提交到代码仓库）
2. ✅ 不要在代码中硬编码Token
3. ✅ 使用配置文件时，确保.gitignore包含config.py（如果包含敏感信息）
4. ✅ 定期更换Token（如果可能）
5. ✅ 不要将Token分享给他人

### 其他问题

#### Q: 数据获取失败怎么办？

A: 
1. 检查网络连接
2. 检查token是否有效（运行 `python test_token.py`）
3. 检查积分是否充足
4. 尝试使用 `--refresh` 参数强制刷新
5. 查看错误信息，根据提示解决问题

#### Q: 如何清理缓存？

A: 删除 `cache/` 目录下的文件即可，或使用缓存管理工具。

#### Q: 程序运行很慢怎么办？

A: 
1. 首次运行会下载数据，需要较长时间
2. 后续运行会使用缓存，速度会快很多
3. 可以调整 `--workers` 参数增加线程数（但要注意tushare的积分限制）
4. 确保网络连接稳定

#### Q: 如何查看Token配置优先级？

程序按以下顺序查找Token：
1. **环境变量** `TUSHARE_TOKEN`（最高优先级）
2. **配置文件** `config.py` 中的 `TUSHARE_TOKEN`
3. **代码中设置** `ts.set_token()`

如果三种方式都配置了，程序会优先使用环境变量。

## 许可证

本项目仅供学习和研究使用。

## 快速配置检查清单

在开始使用前，请确认：

- [ ] 已在Tushare官网注册账号
- [ ] 已获取Token
- [ ] 已通过环境变量或配置文件设置Token
- [ ] 已运行 `python test_token.py` 验证Token有效
- [ ] 已检查积分是否充足
- [ ] 已确认网络连接正常

完成以上步骤后，您就可以正常使用股票选股程序了！

## 需要帮助？

如果遇到问题，请检查：
1. Token是否正确配置（运行 `python test_token.py`）
2. 网络连接是否正常
3. Tushare服务是否正常（访问官网查看）
4. 积分是否充足

更多信息请参考：
- [Tushare官方文档](https://tushare.pro/document/1)
- [Tushare API文档](https://tushare.pro/document/2)

## 更新日志

### v1.0.0 (2024-12-15)
- 初始版本
- 基于tushare实现数据获取
- 支持多维度打分策略
- 支持本地缓存机制
- 支持数据预加载
- 完整的Token配置指南和测试工具

