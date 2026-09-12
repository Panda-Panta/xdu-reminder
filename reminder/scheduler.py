from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from datetime import datetime

from services.semester import SemesterService
from services.classtable import ClassTableService
from services.exam import ExamService
from services.energy import EnergyService
from reminder.class_reminder import ClassReminder
from reminder.exam_reminder import ExamReminder
from reminder.energy_reminder import EnergyReminder

class ReminderScheduler:
    def __init__(self, ids_session, config, notify_manager, data_dir):
        self.scheduler = BackgroundScheduler(timezone='Asia/Shanghai')
        self.ids_session = ids_session
        self.config = config
        self.notify_manager = notify_manager
        self.data_dir = data_dir
        
        self.semester_service = SemesterService(ids_session)
        self.classtable_service = ClassTableService(ids_session, data_dir)
        self.exam_service = ExamService(ids_session, data_dir)
        self.energy_service = EnergyService(ids_session, data_dir)
        
        self.class_reminder = ClassReminder(notify_manager, config)
        self.exam_reminder = ExamReminder(notify_manager, config)
        self.energy_reminder = EnergyReminder(notify_manager, config)
        
        self.semester_code = None
        self.classtable_data = None
        self.exam_data = None
        self.energy_info = None
        self.last_sync_time = None
        self.sync_errors = {}
        self.username = config.get('account', {}).get('username', '')

    def start(self):
        try:
            self._refresh_semester()
            self._refresh_classtable()
            self._refresh_exam()
            self._check_energy()
            self.last_sync_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            logger.error(f"初始数据获取失败: {e}")
            
        self.scheduler.add_job(self._refresh_classtable, CronTrigger(hour=0, minute=5), id='refresh_classtable')
        self.scheduler.add_job(self._schedule_today_classes, CronTrigger(hour=6, minute=0), id='schedule_classes')
        self.scheduler.add_job(self._refresh_exam, IntervalTrigger(hours=6), id='refresh_exam')
        self.scheduler.add_job(self._check_exam_upcoming, CronTrigger(hour=7, minute=0), id='check_exam')
        
        energy_interval = float(self.config.get('reminder', {}).get('energy_check_interval_hours', 24.1))
        self.scheduler.add_job(self._check_energy, IntervalTrigger(hours=energy_interval), id='check_energy')
        
        self._schedule_today_classes()
        self.scheduler.start()

    def reload_config(self, config=None):
        """热重载提醒配置并即时重新调度"""
        if config is not None:
            self.config = config
        self.username = self.config.get('account', {}).get('username', '')

        # 1. 热重载各个子提醒器
        if hasattr(self.class_reminder, "reload_config"):
            self.class_reminder.reload_config(self.config)
        if hasattr(self.exam_reminder, "reload_config"):
            self.exam_reminder.reload_config(self.config)
        if hasattr(self.energy_reminder, "reload_config"):
            self.energy_reminder.reload_config(self.config)

        # 2. 动态调整电费定时检查频率
        energy_interval = float(self.config.get('reminder', {}).get('energy_check_interval_hours', 24.1))
        if getattr(self.scheduler, "running", False) and self.scheduler.get_job('check_energy'):
            self.scheduler.reschedule_job('check_energy', trigger=IntervalTrigger(hours=energy_interval))
            logger.info(f"电费检查频率已动态调整为每 {energy_interval} 小时一次")

        # 3. 重新计算并调度今日课程提醒
        if self.classtable_data and getattr(self.scheduler, "running", False):
            self._schedule_today_classes()

        # 4. 重新计算并调度考试提醒
        if self.exam_data and getattr(self.scheduler, "running", False):
            self._check_exam_upcoming()

        logger.info("ReminderScheduler 已成功完成热重载")

    def _refresh_semester(self):
        self.semester_code = self.semester_service.get_current_semester()
        logger.info(f"刷新学期成功: {self.semester_code}")

    def _refresh_classtable(self):
        if not self.semester_code: return
        try:
            self.classtable_data = self.classtable_service.fetch(self.semester_code, self.username)
            self.sync_errors.pop('classtable', None)
            logger.info("刷新课表成功")
        except Exception as e:
            self.sync_errors['classtable'] = str(e)
            logger.error(f"刷新课表失败: {e}")

    def _schedule_today_classes(self):
        if not self.classtable_data: return
        self.class_reminder.get_today_reminders(self.classtable_data, self.scheduler)
        logger.info("今日课程提醒已调度")

    def _refresh_exam(self):
        if not self.semester_code: return
        try:
            self.exam_data = self.exam_service.fetch(self.semester_code)
            self.sync_errors.pop('exam', None)
            logger.info("刷新考试安排成功")
        except Exception as e:
            self.sync_errors['exam'] = str(e)
            logger.error(f"刷新考试安排失败: {e}")

    def _check_exam_upcoming(self):
        if not self.exam_data: return
        self.exam_reminder.check_and_schedule(self.exam_data, self.scheduler)
        logger.info("考试提醒已检查和调度")

    def _check_energy(self):
        try:
            info = self.energy_service.fetch(self.username)
            self.energy_info = info
            self.sync_errors.pop('energy', None)
            self.energy_reminder.check(info)
            logger.info(f"电费已检查: 剩余 {info.electricity_remain:.1f} 度")
        except Exception as e:
            self.sync_errors['energy'] = str(e)
            logger.error(f"检查电费失败: {e}")

    def sync_all(self):
        """手动全量刷新所有数据"""
        errors = {}
        try:
            self._refresh_semester()
        except Exception as e:
            errors['semester'] = str(e)

        try:
            self._refresh_classtable()
            self._schedule_today_classes()
        except Exception as e:
            errors['classtable'] = str(e)

        try:
            self._refresh_exam()
            self._check_exam_upcoming()
        except Exception as e:
            errors['exam'] = str(e)

        try:
            self._check_energy()
        except Exception as e:
            errors['energy'] = str(e)

        self.last_sync_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return errors

    def get_summary(self):
        """获取当前同步的综合数据概览，供 Web UI 与 API 使用"""
        import os
        import json

        today_classes = []
        total_courses = 0
        term_start = ""
        ct_data = self.classtable_data or self.classtable_service.get_cache()
        if ct_data:
            total_courses = len(ct_data.class_details)
            term_start = ct_data.term_start_day
            today_classes = self.classtable_service.get_today_classes(ct_data)

        energy_data = None
        if self.energy_info:
            energy_data = {
                "remain": self.energy_info.electricity_remain,
                "read_date": self.energy_info.last_read_date,
                "is_low": self.energy_info.electricity_remain < float(self.config.get("reminder", {}).get("energy_threshold", 100)),
                "error": None
            }
        else:
            cached_energy_file = os.path.join(self.data_dir, 'cache', 'energy.json')
            if os.path.exists(cached_energy_file):
                try:
                    with open(cached_energy_file, 'r', encoding='utf-8') as f:
                        ed = json.load(f)
                        energy_data = {
                            "remain": float(ed.get("electricity_remain", 0.0)),
                            "read_date": str(ed.get("last_read_date", "")),
                            "is_low": float(ed.get("electricity_remain", 0.0)) < float(self.config.get("reminder", {}).get("energy_threshold", 100)),
                            "cached": True,
                            "error": self.sync_errors.get("energy")
                        }
                except Exception:
                    pass
            if not energy_data and "energy" in self.sync_errors:
                energy_data = {"error": self.sync_errors["energy"]}

        exam_list = []
        if self.exam_data:
            for s in self.exam_data.subjects:
                exam_list.append({
                    "subject": s.subject,
                    "type": s.type_str,
                    "time": s.time_str,
                    "place": s.place,
                    "seat": s.seat,
                })

        return {
            "semester_code": self.semester_code,
            "term_start_day": term_start,
            "total_courses": total_courses,
            "today_classes": today_classes,
            "energy": energy_data,
            "exams": exam_list,
            "last_sync_time": self.last_sync_time,
            "sync_errors": self.sync_errors,
        }

    def stop(self):
        self.scheduler.shutdown()
        logger.info("调度器已停止")
