"""
Windows 系统原生 Toast 通知渠道
"""
import sys
from typing import Any
from loguru import logger
from notifiers.base import BaseNotifier


class WindowsToastNotifier(BaseNotifier):
    """Windows 原生 Toast 通知渠道"""
    name: str = 'windows_toast'

    def __init__(self) -> None:
        """
        初始化 Windows Toast 通知渠道
        检查当前平台是否为 Windows，并检查 win11toast 模块是否已安装
        """
        self.available: bool = False
        if sys.platform != 'win32':
            logger.warning("WindowsToastNotifier 仅支持 Windows 平台，当前平台已跳过")
            return

        try:
            import win11toast  # noqa: F401
            self.available = True
        except ImportError as e:
            logger.warning(f"未安装 win11toast 模块，WindowsToastNotifier 已禁用: {e}")
            self.available = False

    def send(self, title: str, content: str, **kwargs: Any) -> bool:
        """
        发送 Windows Toast 通知

        :param title: 通知标题
        :param content: 通知内容
        :param kwargs: 传递给 win11toast.toast 的额外参数
        :return: 是否发送成功
        """
        if not self.available:
            logger.warning("WindowsToastNotifier 当前不可用，跳过发送")
            return False

        try:
            import win11toast
            win11toast.toast(title, content, **kwargs)
            return True
        except Exception as e:
            logger.error(f"Windows Toast 发送失败: {e}")
            return False
