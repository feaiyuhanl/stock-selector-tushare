"""
企业微信通知模块 - 基于企业微信机器人Webhook
"""

import json
import os
import sys
import requests
from datetime import datetime
from typing import List, Optional

# 添加上级目录到路径，以便导入config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from .base import BaseNotifier


class WeChatNotifier(BaseNotifier):
    """企业微信通知器"""

    def __init__(self):
        """初始化企业微信通知器"""
        super().__init__()
        self.config = getattr(config, 'WECHAT_CONFIG', {})

        # 从环境变量获取Webhook URL，优先级高于配置文件
        self.webhook_url = os.environ.get('WECHAT_WEBHOOK_URL') or self.config.get('webhook_url')

        # 检查配置
        if not self.webhook_url:
            print("[企业微信通知] 未配置Webhook URL，请检查环境变量或config.py中的WECHAT_CONFIG")
            print("[企业微信通知] 环境变量: WECHAT_WEBHOOK_URL")
            print("[企业微信通知] 如何获取: 企业微信 -> 应用与小程序 -> 机器人 -> 添加机器人 -> Webhook")
        else:
            self.available = True
            print("[企业微信通知] 企业微信机器人服务初始化成功")

    def send_notification(self, subject: str, body: str, recipients: List[str] = None) -> bool:
        """
        发送企业微信通知

        Args:
            subject: 通知主题
            body: 通知正文
            recipients: 接收者列表（企业微信机器人推送不需要指定接收者）

        Returns:
            bool: 发送是否成功
        """
        if not self.available:
            print("[企业微信通知] 企业微信服务不可用")
            return False

        try:
            # 构建消息内容
            message = self._format_message(subject, body)

            # 发送请求
            headers = {'Content-Type': 'application/json'}
            response = requests.post(
                self.webhook_url,
                data=json.dumps(message, ensure_ascii=False),
                headers=headers,
                timeout=10
            )

            # 检查响应
            if response.status_code == 200:
                result = response.json()
                if result.get('errcode') == 0:
                    print(f"[企业微信通知] 消息发送成功")
                    return True
                else:
                    print(f"[企业微信通知] 发送失败: {result.get('errmsg', '未知错误')}")
                    return False
            else:
                print(f"[企业微信通知] HTTP请求失败，状态码: {response.status_code}")
                return False

        except requests.exceptions.Timeout:
            print("[企业微信通知] 发送超时")
            return False
        except requests.exceptions.RequestException as e:
            print(f"[企业微信通知] 网络请求错误: {e}")
            return False
        except Exception as e:
            print(f"[企业微信通知] 发送失败: {e}")
            return False

    def _format_message(self, subject: str, body: str) -> dict:
        """
        格式化企业微信消息

        Args:
            subject: 消息主题
            body: 消息正文

        Returns:
            dict: 企业微信消息格式
        """
        # 企业微信消息长度限制：markdown消息不超过4096个字节
        # 这里使用markdown格式，支持更好的文本展示

        # 清理和格式化正文
        formatted_body = body.strip()

        # 如果正文过长，进行截断
        max_length = 4000  # 留出一些余量
        if len(formatted_body) > max_length:
            formatted_body = formatted_body[:max_length] + "\n\n[消息过长，已截断...]"

        # 构建markdown内容
        markdown_content = f"""# {subject}

{formatted_body}

---
*发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
*来源: A股选股程序*
"""

        return {
            "msgtype": "markdown",
            "markdown": {
                "content": markdown_content
            }
        }


def test_wechat_config():
    """测试企业微信配置"""
    print("=== 企业微信配置测试 ===")

    notifier = WeChatNotifier()
    if not notifier.available:
        print("❌ 企业微信服务不可用")
        return False

    # 发送测试消息
    test_subject = "A股选股程序 - 配置测试"
    test_body = """
企业微信配置测试成功！

如果您收到这条消息，说明企业微信机器人配置正确。

配置信息：
- Webhook URL: 已配置 ✓
- 消息类型: Markdown

此消息为自动发送的测试消息。
"""

    success = notifier.send_notification(test_subject, test_body)

    if success:
        print("✅ 测试消息发送成功")
        return True
    else:
        print("❌ 测试消息发送失败")
        return False


def test_env_variables():
    """测试环境变量获取功能"""
    print("=== 企业微信环境变量测试 ===")

    import os
    webhook_url = os.environ.get('WECHAT_WEBHOOK_URL', '未设置')
    if webhook_url != '未设置':
        # 隐藏敏感信息，只显示前几位和后几位
        masked_url = webhook_url[:50] + "..." + webhook_url[-20:] if len(webhook_url) > 70 else webhook_url
        print(f"WECHAT_WEBHOOK_URL: {masked_url}")
    else:
        print("WECHAT_WEBHOOK_URL: 未设置")

    # 测试配置
    notifier = WeChatNotifier()
    print(f"服务可用性: {'可用' if notifier.available else '不可用'}")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--test-env':
        # 测试环境变量功能
        test_env_variables()
    else:
        # 测试企业微信功能
        test_wechat_config()
