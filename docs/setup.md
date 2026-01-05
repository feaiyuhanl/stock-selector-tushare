# 环境配置和安装指南

本文档说明如何配置运行环境和安装依赖。

## 目录

- [依赖安装](#依赖安装)
- [Tushare Token配置](#tushare-token配置)
- [腾讯云邮件推送配置](#腾讯云邮件推送配置)
- [企业微信通知配置](#企业微信通知配置)
- [快速配置检查清单](#快速配置检查清单)

---

## 依赖安装

### 1. 安装Python依赖

```bash
pip install -r requirements.txt
```

### 2. Python版本要求

- Python 3.7 或更高版本

---

## Tushare Token配置

**重要**：使用本程序前，必须先配置tushare token。

### 获取Token

1. 访问 [Tushare官网](https://tushare.pro/register) 注册账号
2. 登录后，进入"接口"页面，复制您的Token
3. 了解积分限制：Tushare采用积分制度管理API访问权限

### 配置方式（三种方式任选一种，优先级从高到低）

#### 方式1：环境变量（推荐）⭐

**Windows PowerShell**：
```powershell
# 临时设置（当前会话有效）
$env:TUSHARE_TOKEN="your_token_here"

# 永久设置（用户级别）
[System.Environment]::SetEnvironmentVariable("TUSHARE_TOKEN", "your_token_here", "User")
```

**Windows CMD**：
```cmd
# 临时设置（当前会话有效）
set TUSHARE_TOKEN=your_token_here

# 永久设置（用户级别，重启CMD后生效）
setx TUSHARE_TOKEN "your_token_here"
```

**Linux/Mac**：
```bash
# 临时设置（当前会话有效）
export TUSHARE_TOKEN="your_token_here"

# 永久设置（添加到 ~/.bashrc 或 ~/.zshrc）
echo 'export TUSHARE_TOKEN="your_token_here"' >> ~/.bashrc
source ~/.bashrc
```

#### 方式2：配置文件

编辑 `config.py` 文件：
```python
TUSHARE_TOKEN = "your_token_here"  # 替换为您的实际Token
```

**注意**：⚠️ 不要将包含Token的config.py提交到Git仓库

#### 方式3：代码中设置

```python
import tushare as ts
ts.set_token('your_token_here')
```

### 验证配置

运行程序测试Token配置是否正确：
```bash
# 尝试运行程序，如果Token配置正确会开始数据获取
python stock_selector.py --top-n 5 --board main
```

如果程序开始正常运行并显示数据获取进度，表示Token配置成功。如果提示Token相关错误，请检查配置。

---

## 腾讯云邮件推送配置

程序支持通过腾讯云邮件推送服务发送执行结果通知。

### 1. 申请腾讯云账号并开通SES服务

1. 访问 [腾讯云官网](https://cloud.tencent.com/) 注册账号
2. 开通 [腾讯云邮件推送服务](https://console.cloud.tencent.com/ses)
3. 完成实名认证和域名验证

### 2. 获取API密钥

1. 进入 [API密钥管理](https://console.cloud.tencent.com/cam/capi)
2. 创建新的密钥对，记录SecretId和SecretKey

### 3. 配置发件人邮箱

1. 在腾讯云SES控制台添加发件人邮箱
2. 完成邮箱验证（腾讯云会发送验证邮件）

### 4. 配置腾讯云密钥

有两种配置方式，推荐使用环境变量方式（更安全）：

#### 方式一：环境变量配置（推荐）

```bash
# Windows PowerShell
$env:TENCENT_SECRET_ID="AKIDxxxxxxxxxxxxxxxxxx"
$env:TENCENT_SECRET_KEY="xxxxxxxxxxxxxxxxxxxxxxxxxx"
$env:TENCENT_FROM_EMAIL="noreply@yourdomain.com"

# Windows CMD
set TENCENT_SECRET_ID=AKIDxxxxxxxxxxxxxxxxxx
set TENCENT_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxx
set TENCENT_FROM_EMAIL=noreply@yourdomain.com

# Linux/Mac
export TENCENT_SECRET_ID="AKIDxxxxxxxxxxxxxxxxxx"
export TENCENT_SECRET_KEY="xxxxxxxxxxxxxxxxxxxxxxxxxx"
export TENCENT_FROM_EMAIL="noreply@yourdomain.com"
```

#### 方式二：配置文件配置

编辑 `config.py` 文件，填写邮件配置：

```python
EMAIL_CONFIG = {
    'enabled': False,  # 运行时通过--email-notify参数启用
    'default_recipients': ['posterhan@126.com'],  # 默认收件人
    'tencent_cloud': {
        'secret_id': None,   # 腾讯云SecretId（可从环境变量TENCENT_SECRET_ID获取）
        'secret_key': None,  # 腾讯云SecretKey（可从环境变量TENCENT_SECRET_KEY获取）
        'region': 'ap-guangzhou',                   # 地域
        'from_email': None,  # 发件人邮箱（可从环境变量TENCENT_FROM_EMAIL获取）
        'from_name': 'A股选股程序',                 # 发件人名称
    }
}
```

> **注意**: 
> - 环境变量配置优先于配置文件配置。如果同时设置了环境变量和配置文件，程序会使用环境变量的值。
> - `from_email` 必须是已在腾讯云SES控制台验证过的发件人邮箱地址。

### 5. 测试邮件配置

```bash
# 运行邮件配置测试
python email_notification.py
```

如果测试成功，会收到测试邮件。

---

## 企业微信通知配置

程序支持通过企业微信机器人发送执行结果通知。

### 1. 获取Webhook URL

1. 打开企业微信 -> 应用与小程序
2. 点击右上角"+" -> 机器人
3. 添加机器人并设置Webhook URL
4. 复制Webhook URL

### 2. 配置Webhook URL

#### 方式一：环境变量配置（推荐）

```bash
# Windows PowerShell
$env:WECHAT_WEBHOOK_URL="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your_key"

# Windows CMD
set WECHAT_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your_key

# Linux/Mac
export WECHAT_WEBHOOK_URL="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your_key"
```

#### 方式二：配置文件配置

编辑 `config.py` 文件：

```python
WECHAT_CONFIG = {
    'enabled': False,  # 运行时通过--wechat-notify参数启用
    'webhook_url': None,  # 企业微信机器人Webhook URL（可从环境变量WECHAT_WEBHOOK_URL获取）
}
```

> **注意**: 环境变量配置优先于配置文件配置。

---

## 快速配置检查清单

在开始使用前，请确认：

- [ ] 已安装Python 3.7+和所有依赖包（运行 `pip install -r requirements.txt`）
- [ ] 已在Tushare官网注册账号
- [ ] 已获取Tushare Token
- [ ] 已通过环境变量或配置文件设置Tushare Token
- [ ] 已运行 `python stock_selector.py --top-n 5 --board main` 验证Token有效
- [ ] 已检查积分是否充足（详见 [Tushare积分说明](tushare.md)）
- [ ] 已确认网络连接正常
- [ ] （可选）如需邮件通知，已配置腾讯云邮件推送服务
- [ ] （可选）如需企业微信通知，已配置企业微信机器人

完成以上步骤后，您就可以正常使用股票选股程序了！

