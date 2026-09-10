"""
SMTP 邮件通知渠道
"""
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any, Union
from loguru import logger
from notifiers.base import BaseNotifier


class EmailNotifier(BaseNotifier):
    """SMTP 邮件通知渠道"""
    name: str = 'email'

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_ssl: bool,
        username: str,
        password: str,
        to_addr: Union[str, list[str]],
    ) -> None:
        """
        初始化 SMTP 邮件通知渠道

        :param smtp_host: SMTP 服务器主机名，如 smtp.qq.com
        :param smtp_port: SMTP 端口，如 465 或 587
        :param smtp_ssl: 是否启用 SSL 加密连接
        :param username: SMTP 用户名/发件人邮箱
        :param password: SMTP 密码或授权码
        :param to_addr: 收件人邮箱地址（单个字符串或字符串列表）
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_ssl = smtp_ssl
        self.username = username
        self.password = password
        self.to_addr = to_addr

    def send(self, title: str, content: str, **kwargs: Any) -> bool:
        """
        发送邮件通知

        :param title: 邮件标题
        :param content: 邮件正文
        :param kwargs: 额外参数
        :return: 是否发送成功
        """
        try:
            message = MIMEText(content, 'plain', 'utf-8')
            message['Subject'] = Header(title, 'utf-8')
            message['From'] = formataddr((Header("XDU Reminder", "utf-8").encode(), self.username))

            if isinstance(self.to_addr, list):
                recipients = self.to_addr
                message['To'] = ", ".join(self.to_addr)
            else:
                recipients = [self.to_addr]
                message['To'] = self.to_addr

            logger.info(f"正在向 {recipients} 发送邮件通知...")

            server: Union[smtplib.SMTP_SSL, smtplib.SMTP]
            if self.smtp_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)
                server.ehlo()
                try:
                    server.starttls()
                    server.ehlo()
                except (smtplib.SMTPNotSupportedError, smtplib.SMTPException) as e:
                    logger.debug(f"SMTP starttls 跳过或不支持: {e}")

            if self.username and self.password:
                server.login(self.username, self.password)

            server.sendmail(self.username, recipients, message.as_string())
            server.quit()
            logger.info("邮件通知发送成功")
            return True
        except Exception as e:
            logger.error(f"邮件通知发送失败: {e}")
            return False
