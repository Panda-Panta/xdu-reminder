"""
Qmsg酱 (QQ消息推送) 通知渠道
"""
from typing import Any
import httpx
from loguru import logger
from notifiers.base import BaseNotifier


class QmsgNotifier(BaseNotifier):
    """Qmsg酱 QQ消息推送通知渠道"""
    name: str = 'qmsg'

    def __init__(self, key: str, qq: str = '') -> None:
        """
        初始化 Qmsg酱 通知渠道

        :param key: Qmsg 密钥
        :param qq: 目标 QQ 号（支持多个以英文逗号分隔）
        """
        self.key = key.strip()
        self.qq = qq.strip()

    def send(self, title: str, content: str, **kwargs: Any) -> bool:
        """
        发送 Qmsg QQ 消息

        :param title: 消息标题
        :param content: 消息正文
        :param kwargs: 额外参数，例如覆盖 qq 等
        :return: 是否发送成功
        """
        if not self.key:
            logger.error("Qmsg Key 为空，无法发送通知")
            return False

        url = f"https://qmsg.zendee.cn/send/{self.key}"
        target_qq = kwargs.get("qq", self.qq)
        data: dict[str, Any] = {
            "msg": f"{title}\n{content}",
            "qq": target_qq,
        }
        for k, v in kwargs.items():
            if k not in data:
                data[k] = v

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, data=data)
                response.raise_for_status()
                res_data = response.json()

            # Qmsg 响应格式: {"success": true, "reason": "操作成功", "code": 200}
            if res_data.get("success") is True or res_data.get("code") == 200:
                logger.info("Qmsg 通知发送成功")
                return True
            else:
                logger.error(f"Qmsg 发送失败: {res_data}")
                return False
        except httpx.HTTPStatusError as e:
            logger.error(f"Qmsg HTTP 请求错误 [状态码 {e.response.status_code}]: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"Qmsg 通知发送异常: {e}")
            return False
