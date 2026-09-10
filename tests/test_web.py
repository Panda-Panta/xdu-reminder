import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from core.config import Config
from web.app import create_app


class TestWebApp(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.config = Config(data_dir=self.data_dir)

        self.mock_ids = MagicMock()
        self.mock_network = MagicMock()
        self.mock_notify = MagicMock()
        self.mock_notify.test_all.return_value = {"console": True}
        self.scheduler_ref = {"scheduler": None}

        self.app = create_app(
            config=self.config,
            ids_session=self.mock_ids,
            network_client=self.mock_network,
            notify_manager=self.mock_notify,
            scheduler_ref=self.scheduler_ref,
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_index_redirects_to_setup_when_unconfigured(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/setup", res.headers.get("Location"))

    def test_setup_page_get(self):
        res = self.client.get("/setup")
        self.assertEqual(res.status_code, 200)
        self.assertIn("系统与服务配置".encode("utf-8"), res.data)

    def test_setup_page_post(self):
        form_data = {
            "username": "21009200001",
            "password": "test_password",
            "class_minutes_before": "30",
            "exam_minutes_before": "30",
            "energy_threshold": "50",
            "energy_check_interval_hours": "4",
            "energy_max_alerts_per_day": "2",
            "console_enabled": "on",
            "windows_toast_enabled": "on",
        }
        res = self.client.post("/setup", data=form_data)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers.get("Location"))
        self.assertEqual(self.config.get("account.username"), "21009200001")
        self.assertTrue(self.config.is_configured)

    def test_status_page(self):
        res = self.client.get("/status")
        self.assertEqual(res.status_code, 200)
        self.assertIn("系统运行状态".encode("utf-8"), res.data)

    def test_api_status_json(self):
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("login_status", data)
        self.assertIn("configured", data)

    def test_api_test_notify(self):
        res = self.client.post("/api/test-notify")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data, {"console": True})
        self.mock_notify.test_all.assert_called_once()

    def test_api_mfa_send_code_without_client(self):
        res = self.client.post("/api/mfa/send-code", json={"type": "sms"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("status"), "error")
        self.assertIn("当前未处于二次认证等待状态", data.get("message", ""))

    def test_api_test_email_empty_credentials(self):
        res = self.client.post("/api/test-email", json={"username": "", "password": ""})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("status"), "error")
        self.assertIn("不能为空", data.get("message", ""))

    def test_mfa_post_transitions_to_logging_in(self):
        # When user submits code via POST /mfa, it should transition status to logging_in
        res = self.client.post("/mfa", data={"code": "123456", "type": "sms"}, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/status", res.headers.get("Location", ""))
        
        status_res = self.client.get("/api/status")
        status_data = status_res.get_json()
        self.assertEqual(status_data.get("login_status"), "logging_in")
        self.assertIn("正在提交二次认证动态码", status_data.get("login_step", ""))


if __name__ == "__main__":
    unittest.main()
