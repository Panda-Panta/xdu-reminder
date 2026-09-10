import tempfile
import unittest
from pathlib import Path
import yaml

from core.config import Config, DEFAULT_CONFIG


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_config(self):
        config = Config(data_dir=self.data_dir)
        self.assertFalse(config.is_configured)
        self.assertEqual(config.get("server.port"), 5800)
        self.assertEqual(config.get("reminder.class_minutes_before"), 30)
        self.assertEqual(config.get("reminder.energy_threshold"), 50)
        self.assertTrue(config.get("notifiers.console.enabled"))

    def test_custom_config_loading_and_saving(self):
        config_file = self.data_dir / "config.yaml"
        custom_data = {
            "account": {"username": "21009200000", "password": "secure_password"},
            "reminder": {"class_minutes_before": 20},
            "notifiers": {"email": {"enabled": True, "to_addr": "student@xdu.edu.cn"}},
        }
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(custom_data, f)

        config = Config(config_path=config_file, data_dir=self.data_dir)
        self.assertTrue(config.is_configured)
        self.assertEqual(config.get("account.username"), "21009200000")
        self.assertEqual(config.get("reminder.class_minutes_before"), 20)
        # 默认值依然被合并保留
        self.assertEqual(config.get("reminder.energy_threshold"), 50)
        self.assertTrue(config.get("notifiers.email.enabled"))
        self.assertEqual(config.get("notifiers.email.to_addr"), "student@xdu.edu.cn")

    def test_update_and_save(self):
        config = Config(data_dir=self.data_dir)
        config.update({
            "account": {"username": "21009299999", "password": "new_password"},
            "reminder": {"energy_threshold": 40},
        })
        self.assertTrue(config.is_configured)
        self.assertEqual(config.get("account.username"), "21009299999")
        self.assertEqual(config.get("reminder.energy_threshold"), 40)

        # 重新从磁盘读取
        reloaded = Config(data_dir=self.data_dir)
        self.assertEqual(reloaded.get("account.username"), "21009299999")
        self.assertEqual(reloaded.get("reminder.energy_threshold"), 40)


if __name__ == "__main__":
    unittest.main()
