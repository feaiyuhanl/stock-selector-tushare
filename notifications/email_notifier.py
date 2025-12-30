"""
邮件通知模块 - 基于腾讯云邮件推送
"""

import base64
import html
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

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
        tencent_config['from_email'] = os.environ.get('TENCENT_FROM_EMAIL') or tencent_config.get('from_email')
        self.tencent_config = tencent_config
        
        # 调试信息：检查配置是否获取成功（不显示完整密钥）
        if tencent_config.get('secret_id'):
            secret_id_preview = tencent_config['secret_id'][:8] + "..." if len(tencent_config['secret_id']) > 8 else tencent_config['secret_id']
            print(f"[邮件通知] SecretId已配置: {secret_id_preview}")
        else:
            print("[邮件通知] SecretId未配置")

        # 检查腾讯云配置
        if not self._check_tencent_config():
            print("[邮件通知] 腾讯云配置不完整，请检查配置")
            print("[邮件通知] 需要设置环境变量或config.py中的配置:")
            print("[邮件通知]   环境变量: TENCENT_SECRET_ID, TENCENT_SECRET_KEY, TENCENT_FROM_EMAIL")
            print("[邮件通知]   或config.py: EMAIL_CONFIG['tencent_cloud']['from_email']")
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
        missing_fields = []
        for field in required_fields:
            value = self.tencent_config.get(field)
            if not value or (isinstance(value, str) and value.strip() == ''):
                missing_fields.append(field)
        
        if missing_fields:
            for field in missing_fields:
                if field == 'from_email':
                    print(f"[邮件通知] 缺少配置: {field} (可通过环境变量TENCENT_FROM_EMAIL或config.py设置)")
                elif field in ['secret_id', 'secret_key']:
                    print(f"[邮件通知] 缺少配置: {field} (可通过环境变量TENCENT_{field.upper()}或config.py设置)")
                else:
                    print(f"[邮件通知] 缺少配置: {field} (可通过环境变量或config.py设置)")
            return False
        return True

    def send_notification(self, subject: str, body: str, recipients: List[str], 
                         stock_data: Optional[List[Dict]] = None, total_stocks: int = 0) -> bool:
        """
        发送邮件通知

        Args:
            subject: 邮件主题
            body: 邮件正文
            recipients: 收件人列表
            stock_data: 股票数据列表（用于模板发送），每个元素是一个字典，包含股票信息
            total_stocks: 分析的股票总数（用于模板中的total_stocks_analyzed占位符）

        Returns:
            bool: 发送是否成功
        """
        if not self.available:
            print("[邮件通知] 邮件服务不可用")
            return False

        if not recipients:
            print("[邮件通知] 未指定收件人")
            return False

        # 过滤掉空字符串和None值
        valid_recipients = [email for email in recipients if email and isinstance(email, str) and email.strip()]
        
        if not valid_recipients:
            print(f"[邮件通知] 收件人列表中无有效的邮箱地址")
            print(f"[邮件通知] 原始收件人列表: {recipients}")
            print("[邮件通知] 请检查：")
            print("[邮件通知] 1. config.py 中的 EMAIL_CONFIG['default_recipients'] 是否配置了有效的邮箱地址")
            print("[邮件通知] 2. 或者通过命令行参数 --notify-to 指定收件人邮箱")
            return False

        try:
            from tencentcloud.ses.v20201002 import models

            # 创建邮件请求
            req = models.SendEmailRequest()

            # 设置发件人
            req.FromEmailAddress = self.tencent_config['from_email']

            # 设置收件人（过滤后的有效地址）
            req.Destination = valid_recipients

            # 设置邮件主题（必填参数）
            req.Subject = subject

            # 检查是否使用模板发送
            use_template = self.tencent_config.get('use_template', False)
            template_id = self.tencent_config.get('template_id')
            
            if use_template and template_id:
                # 使用模板发送
                print(f"[邮件通知] 使用模板发送，模板ID: {template_id}")
                
                # 生成模板数据
                # 使用传入的total_stocks，如果没有则使用stock_data的长度作为后备
                actual_total_stocks = total_stocks if total_stocks > 0 else (len(stock_data) if stock_data else 0)
                template_data = self._generate_template_data(stock_data, body, total_stocks=actual_total_stocks)
                
                # 设置模板
                template = models.Template()
                template.TemplateID = template_id
                template.TemplateData = json.dumps(template_data, ensure_ascii=False)
                
                req.Template = template
                print(f"[邮件通知] 模板数据已生成:")
                print(f"[邮件通知]   - top_stocks_table_rows: {len(template_data.get('top_stocks_table_rows', ''))} 字符")
                print(f"[邮件通知]   - report_time: {template_data.get('report_time', 'N/A')}")
                print(f"[邮件通知]   - total_stocks_analyzed: {template_data.get('total_stocks_analyzed', 0)}")
                print(f"[邮件通知] 模板数据预览: {template.TemplateData[:300]}...")
            else:
                # 使用Simple方式发送（需要自定义发送权限）
                print("[邮件通知] 使用Simple方式发送")
                
                # 确保body不为空且是字符串
                if not body or not isinstance(body, str):
                    print(f"[邮件通知] 邮件内容为空或格式错误: {type(body)}")
                    return False
                
                # 限制内容长度（腾讯云可能有长度限制）
                max_length = 500000  # 500KB，应该足够
                body_length = len(body)
                if body_length > max_length:
                    body = body[:max_length] + "\n\n[内容过长，已截断]"
                    print(f"[邮件通知] 内容已截断至: {len(body)} 字符")
                
                # 设置邮件内容 - 使用 Simple 结构（必须进行Base64编码）
                simple = models.Simple()

                # 对纯文本内容进行Base64编码
                text_base64 = base64.b64encode(body.encode('utf-8')).decode('utf-8')
                simple.Text = text_base64

                # 生成HTML内容并进行Base64编码
                html_body = self._format_html_body(body)
                html_base64 = base64.b64encode(html_body.encode('utf-8')).decode('utf-8')
                simple.Html = html_base64

                print(f"[邮件通知] 内容已Base64编码 - Text: {len(text_base64)}字符, Html: {len(html_base64)}字符")

                req.Simple = simple

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
            elif "WithOutPermission" in error_msg or "必须使用模版发送" in error_msg:
                print("[邮件通知] 权限问题：未开通自定义发送权限")
                print("[邮件通知] 解决方案：")
                print("[邮件通知] 1. 登录腾讯云控制台 -> 邮件推送(SES) -> 发送设置")
                print("[邮件通知] 2. 申请开通自定义发送权限（需要审核）")
                print("[邮件通知] 3. 或者使用模板发送方式（需要先创建邮件模板）")
                print("[邮件通知] 详情请参考：https://console.cloud.tencent.com/ses")
            return False

    def _generate_template_data(self, stock_data: Optional[List[Dict]], body: str, total_stocks: int = 0) -> Dict:
        """
        生成模板数据，将股票列表格式化为HTML表格
        
        Args:
            stock_data: 股票数据列表
            body: 原始文本内容（备用）
            total_stocks: 分析的股票总数
            
        Returns:
            dict: 模板数据字典，包含 top_stocks_table_rows, report_time, total_stocks_analyzed
        """
        report_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 生成表格行HTML（模板中已有表头，只生成数据行）
        if stock_data and len(stock_data) > 0:
            table_rows = []
            for idx, stock in enumerate(stock_data[:10], 1):  # 最多显示10只
                code = stock.get('code', 'N/A')
                name = stock.get('name', 'N/A')
                score = stock.get('score', 0)
                fundamental_score = stock.get('fundamental_score', 0)
                volume_score = stock.get('volume_score', 0)
                price_score = stock.get('price_score', 0)
                current_price = stock.get('current_price')
                pct_change = stock.get('pct_change')
                pe_ratio = stock.get('pe_ratio')
                pb_ratio = stock.get('pb_ratio')
                roe = stock.get('roe')
                revenue_growth = stock.get('revenue_growth')
                profit_growth = stock.get('profit_growth')
                
                # 构建关键亮点：只显示亮点文案，不显示各维度得分
                highlight_comments = []
                
                # 优先级1：估值优势（最重要）
                if pe_ratio is not None and pe_ratio > 0:
                    if pe_ratio < 15:
                        highlight_comments.append('估值极低')
                    elif pe_ratio < 25:
                        highlight_comments.append('估值合理')
                
                if pb_ratio is not None and pb_ratio > 0:
                    if pb_ratio < 1.5:
                        highlight_comments.append('市净率低')
                
                # 优先级2：盈利能力
                if roe is not None:
                    if roe >= 20:
                        highlight_comments.append('盈利优秀')
                    elif roe >= 15:
                        highlight_comments.append('盈利良好')
                
                # 优先级3：成长性
                if revenue_growth is not None and revenue_growth > 20:
                    highlight_comments.append('营收高增')
                if profit_growth is not None and profit_growth > 30:
                    highlight_comments.append('利润高增')
                
                # 优先级4：市场表现
                if pct_change is not None:
                    if pct_change > 5:
                        highlight_comments.append('强势上涨')
                    elif pct_change > 0:
                        highlight_comments.append('上涨趋势')
                
                # 优先级5：综合评分
                if score >= 85:
                    highlight_comments.append('评分优秀')
                elif score >= 75:
                    highlight_comments.append('评分良好')
                
                # 如果没有任何亮点，使用默认评价
                if not highlight_comments:
                    if fundamental_score and fundamental_score > 70:
                        highlight_comments.append('基本面好')
                    elif volume_score and volume_score > 70:
                        highlight_comments.append('成交活跃')
                    elif price_score and price_score > 70:
                        highlight_comments.append('趋势良好')
                    else:
                        highlight_comments.append('价值低估')
                
                # 只显示亮点文案（移动端显示前2个最重要的亮点）
                highlights_str = ' | '.join(highlight_comments[:2])
                
                # 生成表格行（优化移动端显示：调整padding，给股票代码和企业名称更多空间）
                row = f'''<tr>
                    <td style="text-align: center; padding: 8px 4px; vertical-align: top; border: 1px solid #ddd; font-size: 12px;">{idx}</td>
                    <td style="padding: 8px 6px; font-weight: bold; color: #0066cc; vertical-align: top; border: 1px solid #ddd; font-size: 12px; word-break: break-all;">{code}</td>
                    <td style="padding: 8px 6px; vertical-align: top; border: 1px solid #ddd; font-size: 12px; word-break: break-word;">{html.escape(name)}</td>
                    <td style="text-align: center; padding: 8px 4px; font-weight: bold; vertical-align: top; border: 1px solid #ddd; font-size: 13px;">{score:.2f}</td>
                    <td style="padding: 8px 6px; font-size: 11px; color: #555; line-height: 1.4; vertical-align: top; border: 1px solid #ddd; word-break: break-word;">{highlights_str}</td>
                </tr>'''
                table_rows.append(row)
            
            # 只生成表格行（模板中已有table和tbody标签）
            top_stocks_table_rows = '\n'.join(table_rows)
        else:
            # 如果没有股票数据，生成空行提示
            top_stocks_table_rows = '<tr><td colspan="5" style="text-align: center; padding: 20px; color: #999; border: 1px solid #ddd;">未找到符合条件的股票</td></tr>'
        
        return {
            'top_stocks_table_rows': top_stocks_table_rows,
            'report_time': report_time,
            'total_stocks_analyzed': total_stocks if total_stocks > 0 else (len(stock_data) if stock_data else 0),
            # 兼容旧版本占位符
            'content': top_stocks_table_rows,
            'send_time': report_time
        }
    
    def _format_html_body(self, text_body: str) -> str:
        """
        将纯文本转换为HTML格式

        Args:
            text_body: 纯文本内容

        Returns:
            str: HTML格式内容
        """
        # 转义HTML特殊字符
        escaped_body = html.escape(text_body)
        # 将换行符转换为 <br>
        html_content = escaped_body.replace('\n', '<br>\n')
        
        # 使用字符串拼接而不是 f-string，避免内容中的 { } 字符造成问题
        html_body = (
            '<html>\n'
            '<head>\n'
            '    <meta charset="utf-8">\n'
            '    <style>\n'
            '        body { font-family: Arial, sans-serif; line-height: 1.6; }\n'
            '        .header { color: #333; border-bottom: 2px solid #007acc; padding-bottom: 10px; }\n'
            '        .content { margin: 20px 0; }\n'
            '        .footer { color: #666; font-size: 12px; margin-top: 30px; }\n'
            '    </style>\n'
            '</head>\n'
            '<body>\n'
            '    <div class="header">\n'
            '        <h2>A股选股程序通知</h2>\n'
            '    </div>\n'
            '    <div class="content">\n'
            '        ' + html_content + '\n'
            '    </div>\n'
            '    <div class="footer">\n'
            '        <p>此邮件由A股选股程序自动发送</p>\n'
            '        <p>发送时间: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '</p>\n'
            '    </div>\n'
            '</body>\n'
            '</html>'
        )
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
