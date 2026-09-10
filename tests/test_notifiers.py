"""
Unit tests for notifiers package
"""
import sys
import unittest
from unittest.mock import MagicMock, patch

from notifiers.base import BaseNotifier, NotifyManager
from notifiers.console import ConsoleNotifier
from notifiers.windows_toast import WindowsToastNotifier
from notifiers.windows_alert import WindowsAlertNotifier
from notifiers.email_notifier import EmailNotifier
from notifiers.serverchan import ServerChanNotifier
from notifiers.pushplus import PushPlusNotifier
from notifiers.qmsg import QmsgNotifier
from notifiers.bark import BarkNotifier
from notifiers.dingtalk import DingTalkNotifier


class DummySuccessNotifier(BaseNotifier):
    name = "dummy_success"

    def send(self, title: str, content: str, **kwargs) -> bool:
        return True


class DummyFailNotifier(BaseNotifier):
    name = "dummy_fail"

    def send(self, title: str, content: str, **kwargs) -> bool:
        raise RuntimeError("Send failure dummy")


class TestNotifiers(unittest.TestCase):
    def test_base_notifier_and_manager(self):
        manager = NotifyManager()
        self.assertEqual(len(manager.notifiers), 0)

        s_notifier = DummySuccessNotifier()
        f_notifier = DummyFailNotifier()

        manager.add(s_notifier)
        manager.add(f_notifier)
        self.assertEqual(len(manager.notifiers), 2)
        self.assertEqual(manager.get("dummy_success"), s_notifier)
        self.assertIsNone(manager.get("non_existent"))

        # Test send
        results = manager.send("Test Title", "Test Content")
        self.assertEqual(results, {"dummy_success": True, "dummy_fail": False})

        # Test test_all
        test_results = manager.test_all()
        self.assertEqual(test_results, {"dummy_success": True, "dummy_fail": False})

        # Test remove
        self.assertTrue(manager.remove("dummy_fail"))
        self.assertEqual(len(manager.notifiers), 1)
        self.assertFalse(manager.remove("dummy_fail"))

    def test_console_notifier(self):
        notifier = ConsoleNotifier()
        self.assertEqual(notifier.name, "console")
        self.assertTrue(notifier.send("Console Test", "Content here"))
        self.assertTrue(notifier.test())

    def test_windows_toast_notifier(self):
        with patch("sys.platform", "linux"):
            notifier_linux = WindowsToastNotifier()
            self.assertFalse(notifier_linux.available)
            self.assertFalse(notifier_linux.send("Title", "Content"))

        with patch("sys.platform", "win32"):
            with patch.dict(sys.modules, {"win11toast": MagicMock()}):
                import win11toast
                notifier_win = WindowsToastNotifier()
                self.assertTrue(notifier_win.available)
                res = notifier_win.send("Title", "Content")
                self.assertTrue(res)
                win11toast.toast.assert_called_with("Title", "Content")

    @patch("smtplib.SMTP_SSL")
    def test_email_notifier_ssl(self, mock_smtp_ssl):
        server_instance = MagicMock()
        mock_smtp_ssl.return_value = server_instance

        notifier = EmailNotifier(
            smtp_host="smtp.test.com",
            smtp_port=465,
            smtp_ssl=True,
            username="user@test.com",
            password="password123",
            to_addr="receiver@test.com",
        )
        self.assertEqual(notifier.name, "email")
        self.assertTrue(notifier.send("Email Title", "Email Content"))

        mock_smtp_ssl.assert_called_once_with("smtp.test.com", 465, timeout=15)
        server_instance.login.assert_called_once_with("user@test.com", "password123")
        server_instance.sendmail.assert_called_once()
        server_instance.quit.assert_called_once()

    @patch("smtplib.SMTP")
    def test_email_notifier_starttls(self, mock_smtp):
        server_instance = MagicMock()
        mock_smtp.return_value = server_instance

        notifier = EmailNotifier(
            smtp_host="smtp.test.com",
            smtp_port=587,
            smtp_ssl=False,
            username="user@test.com",
            password="password123",
            to_addr=["r1@test.com", "r2@test.com"],
        )
        self.assertTrue(notifier.send("Email Title", "Email Content"))

        mock_smtp.assert_called_once_with("smtp.test.com", 587, timeout=15)
        server_instance.starttls.assert_called_once()
        server_instance.login.assert_called_once_with("user@test.com", "password123")
        server_instance.sendmail.assert_called_once()

    @patch("httpx.Client")
    def test_serverchan_notifier(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "message": "success"}
        mock_client.post.return_value = mock_response

        notifier = ServerChanNotifier(key="SCT123456")
        self.assertEqual(notifier.name, "serverchan")
        self.assertTrue(notifier.send("SCT Title", "SCT Content"))

        mock_client.post.assert_called_once_with(
            "https://sctapi.ftqq.com/SCT123456.send",
            data={"title": "SCT Title", "desp": "SCT Content"},
        )

        # Failure case
        mock_response.json.return_value = {"code": 40001, "message": "bad token"}
        self.assertFalse(notifier.send("SCT Title", "SCT Content"))

        # Empty key case
        empty_notifier = ServerChanNotifier(key="")
        self.assertFalse(empty_notifier.send("T", "C"))

    @patch("httpx.Client")
    def test_pushplus_notifier(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 200, "msg": "请求成功"}
        mock_client.post.return_value = mock_response

        notifier = PushPlusNotifier(token="TOKEN123", topic="topic_a")
        self.assertEqual(notifier.name, "pushplus")
        self.assertTrue(notifier.send("PP Title", "PP Content"))

        mock_client.post.assert_called_once_with(
            "https://www.pushplus.plus/send",
            json={
                "token": "TOKEN123",
                "title": "PP Title",
                "content": "PP Content",
                "template": "txt",
                "topic": "topic_a",
            },
        )

        # Failure case
        mock_response.json.return_value = {"code": 500, "msg": "error"}
        self.assertFalse(notifier.send("PP Title", "PP Content"))

    @patch("httpx.Client")
    def test_qmsg_notifier(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "code": 200}
        mock_client.post.return_value = mock_response

        notifier = QmsgNotifier(key="KEY123", qq="12345678")
        self.assertEqual(notifier.name, "qmsg")
        self.assertTrue(notifier.send("Qmsg Title", "Qmsg Content"))

        mock_client.post.assert_called_once_with(
            "https://qmsg.zendee.cn/send/KEY123",
            data={"msg": "Qmsg Title\nQmsg Content", "qq": "12345678"},
        )

        # Failure case
        mock_response.json.return_value = {"success": False, "code": 400}
        self.assertFalse(notifier.send("Qmsg Title", "Qmsg Content"))

    @patch("httpx.Client")
    def test_bark_notifier(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 200, "message": "success"}
        mock_client.post.return_value = mock_response

        notifier = BarkNotifier(key="BARK_KEY", server="https://api.day.app/")
        self.assertEqual(notifier.name, "bark")
        self.assertTrue(notifier.send("Bark Title", "Bark Content"))

        mock_client.post.assert_called_once_with(
            "https://api.day.app/BARK_KEY",
            json={
                "title": "Bark Title",
                "body": "Bark Content",
                "group": "XDU Reminder",
            },
        )

        # Failure case
        mock_response.json.return_value = {"code": 400, "message": "failed"}
        self.assertFalse(notifier.send("Bark Title", "Bark Content"))

    @patch("httpx.Client")
    def test_dingtalk_notifier(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"errcode": 0, "errmsg": "ok"}
        mock_client.post.return_value = mock_response

        # Webhook without secret
        notifier_no_sec = DingTalkNotifier(webhook="https://oapi.dingtalk.com/robot/send?access_token=123")
        self.assertEqual(notifier_no_sec.name, "dingtalk")
        self.assertTrue(notifier_no_sec.send("DT Title", "DT Content"))

        mock_client.post.assert_called_once_with(
            "https://oapi.dingtalk.com/robot/send?access_token=123",
            json={
                "msgtype": "text",
                "text": {"content": "DT Title\nDT Content"},
            },
        )

        # Webhook with secret
        mock_client.reset_mock()
        notifier_with_sec = DingTalkNotifier(
            webhook="https://oapi.dingtalk.com/robot/send?access_token=123",
            secret="SEC123456",
        )
        self.assertTrue(notifier_with_sec.send("DT Title", "DT Content"))
        called_url = mock_client.post.call_args[0][0]
        self.assertIn("timestamp=", called_url)
        self.assertIn("sign=", called_url)

        # Failure response
        mock_response.json.return_value = {"errcode": 300001, "errmsg": "token is not exist"}
        self.assertFalse(notifier_no_sec.send("DT Title", "DT Content"))

    def test_windows_alert_notifier(self):
        notifier = WindowsAlertNotifier(timeout=10)
        self.assertEqual(notifier.name, "windows_alert")
        # On Windows, send should return True (spawns background popup thread)
        if sys.platform == "win32":
            self.assertTrue(notifier.supported)
            self.assertTrue(notifier.send("Test Title", "Test Content"))
        else:
            self.assertFalse(notifier.supported)
            self.assertFalse(notifier.send("Test Title", "Test Content"))


if __name__ == "__main__":
    unittest.main()
