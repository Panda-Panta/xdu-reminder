"""
PushPlus (微信推送) 通知渠道
"""
from typing import Any, Optional
import httpx
from loguru import logger
from notifiers.base import BaseNotifier


class PushPlusNotifier(BaseNotifier):
    """PushPlus 微信推送通知渠道"""
    name: str = 'pushplus'

    def __init__(self, token: str, topic: Optional[str] = None, template: str = 'txt') -> None:
        """
        初始化 PushPlus 通知渠道

        :param token: PushPlus 用户 Token
        :param topic: 群组编码（可选）
        :param template: 发送模板，默认为 'txt'，可选 'html', 'json', 'markdown' 等
        """
        self.token = token.strip()
        self.topic = topic
        self.template = template

    def send(self, title: str, content: str, **kwargs: Any) -> bool:
        """
        发送 PushPlus 通知

        :param title: 消息标题
        :param content: 消息内容
        :param kwargs: 额外参数，如 topic, template, channel 等
        :return: 是否发送成功
        """
        if not self.token:
            logger.error("PushPlus Token 为空，无法发送通知")
            return False

        url = "https://www.pushplus.plus/send"
        payload: dict[str, Any] = {
            "token": self.token,
            "title": title,
            "content": content,
            "template": kwargs.get("template", self.template),
        }
        if self.topic:
            payload["topic"] = self.topic

        for k, v in kwargs.items():
            if k not in payload:
                payload[k] = v

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                res_data = response.json()

            if res_data.get("code") == 200:
                logger.info("PushPlus 通知发送成功")
                return True
            else:
                logger.error(f"PushPlus 发送失败: {res_data}")
                return False
        except httpx.HTTPStatusError as e:
            logger.error(f"PushPlus HTTP 请求错误 [状态码 {e.response.status_code}]: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"PushPlus 通知发送异常: {e}")
            return False
