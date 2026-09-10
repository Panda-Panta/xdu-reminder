"""
Bark (iOS 设备推送) 通知渠道
"""
from typing import Any
import httpx
from loguru import logger
from notifiers.base import BaseNotifier


class BarkNotifier(BaseNotifier):
    """Bark (iOS 推送客户端) 通知渠道"""
    name: str = 'bark'

    def __init__(self, key: str, server: str = 'https://api.day.app') -> None:
        """
        初始化 Bark 通知渠道

        :param key: Bark 设备 Key
        :param server: Bark 服务器地址，默认为官方服务器 https://api.day.app
        """
        self.key = key.strip()
        self.server = server.rstrip('/')

    def send(self, title: str, content: str, **kwargs: Any) -> bool:
        """
        发送 Bark 消息推送

        :param title: 消息标题
        :param content: 消息内容
        :param kwargs: 额外参数，如 icon, sound, badge, url 等
        :return: 是否发送成功
        """
        if not self.key:
            logger.error("Bark Key 为空，无法发送通知")
            return False

        url = f"{self.server}/{self.key}"
        payload: dict[str, Any] = {
            "title": title,
            "body": content,
            "group": kwargs.get("group", "XDU Reminder"),
        }
        for k, v in kwargs.items():
            if k not in payload:
                payload[k] = v

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                res_data = response.json()

            # Bark 返回格式: {"code": 200, "message": "success", "timestamp": ...}
            if res_data.get("code") == 200:
                logger.info("Bark 通知发送成功")
                return True
            else:
                logger.error(f"Bark 发送失败: {res_data}")
                return False
        except httpx.HTTPStatusError as e:
            logger.error(f"Bark HTTP 请求错误 [状态码 {e.response.status_code}]: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"Bark 通知发送异常: {e}")
            return False
