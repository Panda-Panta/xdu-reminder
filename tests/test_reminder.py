from datetime import datetime, timedelta, date
import unittest
from unittest.mock import MagicMock

from reminder.class_reminder import ClassReminder
from reminder.exam_reminder import ExamReminder
from reminder.energy_reminder import EnergyReminder
from services.classtable import ClassTableData, ClassDetail, TimeArrangement
from services.exam import ExamData, ExamSubject
from services.energy import EnergyInfo


class TestReminders(unittest.TestCase):
    def setUp(self):
        self.mock_notifier = MagicMock()
        self.config = {
            "reminder": {
                "class_minutes_before": 30,
                "exam_minutes_before": 30,
                "exam_day_before_notify": True,
                "energy_threshold": 50,
                "energy_max_alerts_per_day": 2,
            }
        }

    def test_energy_reminder_threshold(self):
        reminder = EnergyReminder(self.mock_notifier, self.config)

        # 余额 60度 (>= 50)，不提醒
        reminder.check(EnergyInfo(electricity_remain=60.0, last_read_date="2026-09-10"))
        self.mock_notifier.send.assert_not_called()

        # 余额 35度 (< 50)，触发提醒
        reminder.check(EnergyInfo(electricity_remain=35.0, last_read_date="2026-09-10"))
        self.assertEqual(self.mock_notifier.send.call_count, 1)

        # 余额 30度 (< 50)，第二次触发提醒
        reminder.check(EnergyInfo(electricity_remain=30.0, last_read_date="2026-09-10"))
        self.assertEqual(self.mock_notifier.send.call_count, 2)

        # 第三次检查 (< 50)，由于达到当天最多2次提醒限制，不重复轰炸
        reminder.check(EnergyInfo(electricity_remain=25.0, last_read_date="2026-09-10"))
        self.assertEqual(self.mock_notifier.send.call_count, 2)

    def test_exam_reminder_scheduling(self):
        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = None

        reminder = ExamReminder(self.mock_notifier, self.config)

        now = datetime.now()
        # 安排一场 2 天后的考试
        future_exam_time = now + timedelta(days=2)
        exam_data = ExamData(
            subjects=[
                ExamSubject(
                    subject="高等数学",
                    type_str="期末考试",
                    time_str=future_exam_time.strftime("%Y-%m-%d %H:%M-%H:%M"),
                    place="J-101",
                    seat="05",
                    start_time=future_exam_time,
                    end_time=future_exam_time + timedelta(hours=2),
                )
            ]
        )

        reminder.check_and_schedule(exam_data, mock_scheduler)
        # 应注册考前一天 20:00 提醒与考前 30 分钟提醒两个任务
        self.assertTrue(mock_scheduler.add_job.called)
        self.assertGreaterEqual(mock_scheduler.add_job.call_count, 1)

    def test_class_reminder_send(self):
        reminder = ClassReminder(self.mock_notifier, self.config)
        sample_class = {
            "name": "大学物理",
            "start_time": "14:00",
            "end_time": "15:35",
            "classroom": "E-II-201",
            "teacher": "张教授",
            "period_start": 5,
        }
        reminder._send_class_reminder(sample_class)
        self.mock_notifier.send.assert_called_once()
        args, kwargs = self.mock_notifier.send.call_args
        self.assertIn("大学物理", kwargs.get("title", ""))
        self.assertIn("E-II-201", kwargs.get("content", ""))


if __name__ == "__main__":
    unittest.main()
