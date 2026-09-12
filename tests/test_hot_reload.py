import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock
import yaml

from core.config import Config
from reminder.scheduler import ReminderScheduler
from notifiers import NotifyManager
from web.app import create_app


class TestHotReload(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.config_path = self.data_dir / 'config.yaml'
        
        initial_data = {
            'account': {
                'username': '21009200001',
                'password': 'test_password',
            },
            'reminder': {
                'class_minutes_before': 30,
                'exam_minutes_before': 30,
                'exam_day_before_notify': True,
                'energy_threshold': 100,
                'energy_check_interval_hours': 24.1,
                'energy_max_alerts_per_day': 2,
            },
            'notifiers': {
                'console': {'enabled': True},
                'windows_alert': {'enabled': False},
            }
        }
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(initial_data, f)
            
        self.config = Config(config_path=self.config_path, data_dir=self.data_dir)
        self.mock_ids = MagicMock()
        self.mock_notify = NotifyManager()

    def tearDown(self):
        if hasattr(self.config, 'stop_file_watcher'):
            self.config.stop_file_watcher()
        self.temp_dir.cleanup()

    def test_scheduler_hot_reloads_parameters(self):
        sched = ReminderScheduler(
            ids_session=self.mock_ids,
            config=self.config,
            notify_manager=self.mock_notify,
            data_dir=str(self.data_dir),
        )
        
        self.assertEqual(sched.class_reminder.minutes_before, 30)
        self.assertEqual(sched.exam_reminder.minutes_before, 30)
        self.assertEqual(sched.energy_reminder.threshold, 100.0)
        
        self.config.update({
            'reminder': {
                'class_minutes_before': 15,
                'exam_minutes_before': 45,
                'energy_threshold': 80,
                'energy_check_interval_hours': 12.5,
            }
        })
        
        sched.reload_config(self.config)
        
        self.assertEqual(sched.class_reminder.minutes_before, 15)
        self.assertEqual(sched.exam_reminder.minutes_before, 45)
        self.assertEqual(sched.energy_reminder.threshold, 80.0)

    def test_config_change_listeners(self):
        callback_mock = MagicMock()
        self.config.add_change_listener(callback_mock)
        
        self.config.update({'reminder': {'energy_threshold': 120}})
        callback_mock.assert_called_once_with(self.config)
        self.assertEqual(self.config.get('reminder.energy_threshold'), 120)

    def test_file_watcher_detects_external_change(self):
        callback_mock = MagicMock()
        self.config.add_change_listener(callback_mock)
        self.config.start_file_watcher(interval=0.1)
        
        # Wait a tiny bit and update file on disk directly
        time.sleep(0.15)
        with open(self.config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        data['reminder']['energy_threshold'] = 66
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f)
            
        # Give watcher up to 1 second to detect
        for _ in range(15):
            time.sleep(0.1)
            if self.config.get('reminder.energy_threshold') == 66:
                break
                
        self.assertEqual(self.config.get('reminder.energy_threshold'), 66)
        self.assertTrue(callback_mock.called)
        self.config.stop_file_watcher()

    def test_web_setup_post_hot_reloads_when_already_logged_in(self):
        mock_ids = MagicMock()
        mock_net = MagicMock()
        mock_notify = NotifyManager()
        sched_mock = MagicMock()
        scheduler_ref = {'scheduler': sched_mock}
        
        app = create_app(
            config=self.config,
            ids_session=mock_ids,
            network_client=mock_net,
            notify_manager=mock_notify,
            scheduler_ref=scheduler_ref,
        )
        app.app_state['login_status'] = 'logged_in'
        client = app.test_client()
        
        form_data = {
            'username': '21009200001',
            'password': 'test_password',
            'class_minutes_before': '20',
            'exam_minutes_before': '40',
            'energy_threshold': '150',
            'energy_check_interval_hours': '24.1',
            'energy_max_alerts_per_day': '3',
            'console_enabled': 'on',
            'windows_alert_enabled': 'on',
        }
        res = client.post('/setup', data=form_data, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        # Should redirect to /status with reloaded=1 without calling login!
        self.assertIn('/status', res.headers.get('Location'))
        self.assertIn('reloaded=1', res.headers.get('Location'))
        mock_ids.login.assert_not_called()
        
        # Verify config updated
        self.assertEqual(self.config.get('reminder.class_minutes_before'), 20)
        self.assertEqual(self.config.get('reminder.energy_threshold'), 150.0)
        self.assertTrue(self.config.get('notifiers.windows_alert.enabled'))
        
        # Verify scheduler reload was called
        sched_mock.reload_config.assert_called_with(self.config)


if __name__ == '__main__':
    unittest.main()
