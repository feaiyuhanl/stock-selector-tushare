"""
邮件通知模块 - 基于腾讯云邮件推送
"""

import json
import os
import sys
from datetime import datetime
from typing import List, Optional

# 添加上级目录到路径，以便导入config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from .base import BaseNotifier


class EmailNotifier(BaseNotifier):
    """邮件通知器"""

    def __init__(self):
        """初始化邮件通知器"""
        super().__init__()
        self.config = config.EMAIL_CONFIG

        # 从环境变量获取腾讯云密钥，优先级高于配置文件
        tencent_config = self.config['tencent_cloud'].copy()
        tencent_config['secret_id'] = os.environ.get('TENCENT_SECRET_ID') or tencent_config.get('secret_id')
        tencent_config['secret_key'] = os.environ.get('TENCENT_SECRET_KEY') or tencent_config.get('secret_key')
        self.tencent_config = tencent_config
        
        # 调试信息：检查配置是否获取成功（不显示完整密钥）
        if tencent_config.get('secret_id'):
            secret_id_preview = tencent_config['secret_id'][:8] + "..." if len(tencent_config['secret_id']) > 8 else tencent_config['secret_id']
            print(f"[邮件通知] SecretId已配置: {secret_id_preview}")
        else:
            print("[邮件通知] SecretId未配置")

        # 检查腾讯云配置
        if not self._check_tencent_config():
            print("[邮件通知] 腾讯云配置不完整，请检查环境变量或config.py中的EMAIL_CONFIG")
            print("[邮件通知] 环境变量: TENCENT_SECRET_ID, TENCENT_SECRET_KEY")
            return
        else:
            try:
                from tencentcloud.common import credential
                from tencentcloud.common.profile.client_profile import ClientProfile
                from tencentcloud.common.profile.http_profile import HttpProfile
                from tencentcloud.ses.v20201002 import ses_client, models

                # 创建腾讯云客户端
                # 确保 SecretId 和 SecretKey 不为空
                secret_id = self.tencent_config['secret_id'].strip() if isinstance(self.tencent_config['secret_id'], str) else self.tencent_config['secret_id']
                secret_key = self.tencent_config['secret_key'].strip() if isinstance(self.tencent_config['secret_key'], str) else self.tencent_config['secret_key']
                
                if not secret_id or not secret_key:
                    print("[邮件通知] SecretId 或 SecretKey 为空，请检查配置")
                    return
                
                cred = credential.Credential(
                    secret_id,
                    secret_key
                )

                http_profile = HttpProfile()
                http_profile.endpoint = "ses.tencentcloudapi.com"

                client_profile = ClientProfile()
                client_profile.httpProfile = http_profile

                self.client = ses_client.SesClient(cred, self.tencent_config['region'], client_profile)
                print("[邮件通知] 腾讯云邮件服务初始化成功")
                self.available = True

            except ImportError:
                print("[邮件通知] 未安装腾讯云SDK，请运行: pip install tencentcloud-sdk-python")
            except Exception as e:
                print(f"[邮件通知] 腾讯云客户端初始化失败: {e}")

    def _check_tencent_config(self) -> bool:
        """检查腾讯云配置是否完整"""
        required_fields = ['secret_id', 'secret_key', 'from_email']
        for field in required_fields:
            value = self.tencent_config.get(field)
            if not value or (isinstance(value, str) and value.strip() == ''):
                print(f"[邮件通知] 缺少腾讯云配置: {field}")
                return False
        return True

    def send_notification(self, subject: str, body: str, recipients: List[str]) -> bool:
        """
        发送邮件通知

        Args:
            subject: 邮件主题
            body: 邮件正文
            recipients: 收件人列表

        Returns:
            bool: 发送是否成功
        """
        if not self.available:
            print("[邮件通知] 邮件服务不可用")
            return False

        if not recipients:
            print("[邮件通知] 未指定收件人")
            return False

        try:
            from tencentcloud.ses.v20201002 import models

            # 创建邮件请求
            req = models.SendEmailRequest()

            # 设置发件人
            req.FromEmailAddress = self.tencent_config['from_email']
            req.FromEmailAddressName = self.tencent_config['from_name']

            # 设置收件人
            req.Destination = recipients

            # 设置邮件内容
            req.Subject = subject
            req.HtmlBody = self._format_html_body(body)
            req.TextBody = body  # 纯文本版本

            # 发送邮件
            resp = self.client.SendEmail(req)

            # 检查响应
            if resp.MessageId:
                print(f"[邮件通知] 邮件发送成功，消息ID: {resp.MessageId}")
                return True
            else:
                print("[邮件通知] 邮件发送失败，无效响应")
                return False

        except Exception as e:
            error_msg = str(e)
            print(f"[邮件通知] 发送邮件失败: {error_msg}")
            
            # 提供更详细的错误提示
            if "SecretId" in error_msg or "AuthFailure" in error_msg:
                print("[邮件通知] 认证失败，请检查：")
                print("[邮件通知] 1. SecretId 和 SecretKey 是否正确配置")
                print("[邮件通知] 2. 环境变量 TENCENT_SECRET_ID 和 TENCENT_SECRET_KEY 是否设置")
                print("[邮件通知] 3. SecretId 和 SecretKey 是否在腾讯云控制台正确创建")
                print("[邮件通知] 4. 是否在腾讯云控制台开通了SES邮件推送服务")
                print("[邮件通知] 5. SecretId 是否有SES服务的访问权限")
            return False

    def _format_html_body(self, text_body: str) -> str:
        """
        将纯文本转换为HTML格式

        Args:
            text_body: 纯文本内容

        Returns:
            str: HTML格式内容
        """
        # 简单的文本到HTML转换
        html_body = text_body.replace('\n', '<br>')
        html_body = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .header {{ color: #333; border-bottom: 2px solid #007acc; padding-bottom: 10px; }}
                .content {{ margin: 20px 0; }}
                .footer {{ color: #666; font-size: 12px; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>A股选股程序通知</h2>
            </div>
            <div class="content">
                {html_body}
            </div>
            <div class="footer">
                <p>此邮件由A股选股程序自动发送</p>
                <p>发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
        </body>
        </html>
        """
        return html_body


def test_email_config():
    """测试邮件配置"""
    print("=== 邮件配置测试 ===")

    notifier = EmailNotifier()
    if not notifier.available:
        print("❌ 邮件服务不可用")
        return False

    # 发送测试邮件
    test_subject = "A股选股程序 - 配置测试"
    test_body = """
邮件配置测试成功！

如果您收到这封邮件，说明腾讯云邮件服务配置正确。

配置信息：
- 发件人: {from_email}
- 收件人: {recipients}
- 地域: {region}

此邮件为自动发送的测试邮件，无需回复。
""".format(
        from_email=config.EMAIL_CONFIG['tencent_cloud']['from_email'],
        recipients=', '.join(config.EMAIL_CONFIG['default_recipients']),
        region=config.EMAIL_CONFIG['tencent_cloud']['region']
    )

    success = notifier.send_notification(
        test_subject,
        test_body,
        config.EMAIL_CONFIG['default_recipients']
    )

    if success:
        print("✅ 测试邮件发送成功")
        return True
    else:
        print("❌ 测试邮件发送失败")
        return False


def test_env_variables():
    """测试环境变量获取功能"""
    print("=== 环境变量测试 ===")

    import os
    print(f"TENCENT_SECRET_ID: {os.environ.get('TENCENT_SECRET_ID', '未设置')}")
    print(f"TENCENT_SECRET_KEY: {os.environ.get('TENCENT_SECRET_KEY', '未设置')}")

    # 测试配置合并
    notifier = EmailNotifier()
    if hasattr(notifier, 'tencent_config'):
        print(f"配置中的secret_id: {notifier.tencent_config.get('secret_id', '未设置')}")
        print(f"配置中的secret_key: {notifier.tencent_config.get('secret_key', '未设置')}")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--test-env':
        # 测试环境变量功能
        test_env_variables()
    else:
        # 测试邮件功能
        test_email_config()
