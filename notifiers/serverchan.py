"""
Server酱 (微信推送) 通知渠道
"""
from typing import Any
import httpx
from loguru import logger
from notifiers.base import BaseNotifier


class ServerChanNotifier(BaseNotifier):
    """Server酱微信推送通知渠道"""
    name: str = 'serverchan'

    def __init__(self, key: str) -> None:
        """
        初始化 Server酱 通知渠道

        :param key: Server酱 SendKey (如 SCTxxxxxxxx 或旧版 SCUxxxxxxxx)
        """
        self.key = key.strip()

    def send(self, title: str, content: str, **kwargs: Any) -> bool:
        """
        发送 Server酱 消息

        :param title: 消息标题
        :param content: 消息内容（支持 Markdown）
        :param kwargs: 额外参数，例如 channel, openid 等
        :return: 是否发送成功
        """
        if not self.key:
            logger.error("Server酱 SendKey 为空，无法发送通知")
            return False

        url = f"https://sctapi.ftqq.com/{self.key}.send"
        data: dict[str, Any] = {
            "title": title,
            "desp": content,
        }
        data.update(kwargs)

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, data=data)
                response.raise_for_status()
                res_data = response.json()

            code = res_data.get("code")
            errno = res_data.get("errno")
            if code == 0 or errno == 0:
                logger.info("Server酱通知发送成功")
                return True
            else:
                logger.error(f"Server酱发送失败: {res_data}")
                return False
        except httpx.HTTPStatusError as e:
            logger.error(f"Server酱 HTTP 请求错误 [状态码 {e.response.status_code}]: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"Server酱通知发送异常: {e}")
            return False
