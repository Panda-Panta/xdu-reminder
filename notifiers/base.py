"""
通知渠道基类与通知管理器
"""
from abc import ABC, abstractmethod
from typing import Any, Optional
from loguru import logger


class BaseNotifier(ABC):
    """通知渠道抽象基类"""
    name: str = 'base'

    @abstractmethod
    def send(self, title: str, content: str, **kwargs: Any) -> bool:
        """
        发送通知，返回是否成功

        :param title: 通知标题
        :param content: 通知正文内容
        :param kwargs: 额外参数
        :return: 是否发送成功
        """
        ...

    def test(self) -> bool:
        """
        发送测试通知

        :return: 测试是否成功
        """
        return self.send('XDU Reminder 测试', '如果你收到了这条消息，说明通知渠道配置成功！')


class NotifyManager:
    """通知管理器，统一管理和批量触发所有注册的通知渠道"""

    def __init__(self) -> None:
        self._notifiers: list[BaseNotifier] = []

    @property
    def notifiers(self) -> list[BaseNotifier]:
        """获取所有已注册的通知渠道"""
        return self._notifiers

    def add(self, notifier: BaseNotifier) -> None:
        """
        注册一个通知渠道

        :param notifier: 实现了 BaseNotifier 的通知渠道实例
        """
        self._notifiers.append(notifier)
        logger.info(f'注册通知渠道: {notifier.name}')

    def remove(self, name: str) -> bool:
        """
        根据名称移除通知渠道

        :param name: 渠道名称
        :return: 是否成功移除
        """
        initial_len = len(self._notifiers)
        self._notifiers = [n for n in self._notifiers if n.name != name]
        removed = len(self._notifiers) < initial_len
        if removed:
            logger.info(f'移除通知渠道: {name}')
        return removed

    def get(self, name: str) -> Optional[BaseNotifier]:
        """
        根据名称获取通知渠道实例

        :param name: 渠道名称
        :return: 对应的通知渠道或 None
        """
        for n in self._notifiers:
            if n.name == name:
                return n
        return None

    def send(self, title: str, content: str, **kwargs: Any) -> dict[str, bool]:
        """
        向所有已注册的通知渠道广播发送通知

        :param title: 通知标题
        :param content: 通知正文
        :param kwargs: 额外参数
        :return: 每个渠道的发送结果字典 {渠道名称: 是否成功}
        """
        results: dict[str, bool] = {}
        for n in self._notifiers:
            try:
                results[n.name] = n.send(title, content, **kwargs)
            except Exception as e:
                logger.error(f'通知发送失败 [{n.name}]: {e}')
                results[n.name] = False
        return results

    def test_all(self) -> dict[str, bool]:
        """
        测试所有已注册的通知渠道

        :return: 每个渠道的测试结果字典 {渠道名称: 是否成功}
        """
        results: dict[str, bool] = {}
        for n in self._notifiers:
            try:
                results[n.name] = n.test()
            except Exception as e:
                logger.error(f'通知测试失败 [{n.name}]: {e}')
                results[n.name] = False
        return results
