"""
控制台/日志通知渠道
"""
from typing import Any
from loguru import logger
from notifiers.base import BaseNotifier


class ConsoleNotifier(BaseNotifier):
    """控制台/日志输出通知渠道"""
    name: str = 'console'

    def send(self, title: str, content: str, **kwargs: Any) -> bool:
        """
        在控制台/日志中输出通知内容

        :param title: 通知标题
        :param content: 通知内容
        :param kwargs: 额外参数
        :return: 是否成功记录
        """
        try:
            logger.info(f"[通知] {title} - {content}")
            return True
        except Exception as e:
            logger.error(f"控制台通知记录失败: {e}")
            return False
