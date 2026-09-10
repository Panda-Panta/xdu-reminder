"""
钉钉自定义机器人 Webhook 通知渠道
"""
import base64
import hashlib
import hmac
import time
import urllib.parse
from typing import Any
import httpx
from loguru import logger
from notifiers.base import BaseNotifier


class DingTalkNotifier(BaseNotifier):
    """钉钉群自定义机器人通知渠道"""
    name: str = 'dingtalk'

    def __init__(self, webhook: str, secret: str = '') -> None:
        """
        初始化钉钉机器人通知渠道

        :param webhook: 钉钉机器人的 Webhook 地址
        :param secret: 加签密钥（可选）
        """
        self.webhook = webhook.strip()
        self.secret = secret.strip()

    def _get_signed_url(self) -> str:
        """
        如果配置了加签密钥，计算签名并附加到 Webhook URL 中

        :return: 完整的请求 URL
        """
        if not self.secret:
            return self.webhook

        timestamp = str(int(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode('utf-8'))

        separator = '&' if '?' in self.webhook else '?'
        return f"{self.webhook}{separator}timestamp={timestamp}&sign={sign}"

    def send(self, title: str, content: str, **kwargs: Any) -> bool:
        """
        发送钉钉群机器人消息

        :param title: 消息标题
        :param content: 消息内容
        :param kwargs: 额外参数，例如 at（@某人配置）
        :return: 是否发送成功
        """
        if not self.webhook:
            logger.error("钉钉 Webhook 地址为空，无法发送通知")
            return False

        target_url = self._get_signed_url()
        full_text = f"{title}\n{content}" if title else content
        payload: dict[str, Any] = {
            "msgtype": "text",
            "text": {
                "content": full_text,
            },
        }

        if "at" in kwargs:
            payload["at"] = kwargs["at"]

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(target_url, json=payload)
                response.raise_for_status()
                res_data = response.json()

            if res_data.get("errcode") == 0:
                logger.info("钉钉机器人通知发送成功")
                return True
            else:
                logger.error(f"钉钉机器人发送失败: {res_data}")
                return False
        except httpx.HTTPStatusError as e:
            logger.error(f"钉钉 HTTP 请求错误 [状态码 {e.response.status_code}]: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"钉钉机器人通知发送异常: {e}")
            return False
