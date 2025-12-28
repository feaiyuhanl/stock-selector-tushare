"""
通知模块基类和工厂函数
"""

from abc import ABC, abstractmethod
from typing import List, Optional


class BaseNotifier(ABC):
    """通知器基类"""

    def __init__(self):
        """初始化通知器"""
        self.available = False

    @abstractmethod
    def send_notification(self, subject: str, body: str, recipients: List[str]) -> bool:
        """
        发送通知

        Args:
            subject: 通知主题
            body: 通知正文
            recipients: 接收者列表

        Returns:
            bool: 发送是否成功
        """
        pass

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.available


def get_notifier(notifier_type: str) -> Optional[BaseNotifier]:
    """
    获取通知器实例

    Args:
        notifier_type: 通知器类型 ('email', 'wechat', 'sms')

    Returns:
        BaseNotifier实例或None（如果不支持或初始化失败）
    """
    notifier_type = notifier_type.lower()

    if notifier_type == 'email':
        try:
            from .email_notifier import EmailNotifier
            return EmailNotifier()
        except ImportError:
            print(f"[通知] 无法加载 {notifier_type} 通知器")
            return None

    elif notifier_type == 'wechat':
        try:
            from .wechat import WeChatNotifier
            return WeChatNotifier()
        except ImportError:
            print(f"[通知] 无法加载 {notifier_type} 通知器")
            return None

    elif notifier_type == 'sms':
        # SMS通知器预留
        print(f"[通知] {notifier_type} 通知器暂未实现")
        return None

    else:
        print(f"[通知] 不支持的通知类型: {notifier_type}")
        print(f"[通知] 支持的类型: email, wechat, sms")
        return None
