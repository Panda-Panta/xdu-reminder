from datetime import datetime, timedelta
from apscheduler.triggers.date import DateTrigger
from loguru import logger

class ExamReminder:
    def __init__(self, notify_manager, config):
        self.notify_manager = notify_manager
        self.config = config
        rem_conf = config.get('reminder', {})
        self.minutes_before = rem_conf.get('exam_minutes_before', 30)
        self.day_before_notify = rem_conf.get('exam_day_before_notify', True)
        self._notified_exams = set()

    def reload_config(self, config=None):
        """热重载考试提醒配置"""
        if config is not None:
            self.config = config
        rem_conf = self.config.get('reminder', {})
        self.minutes_before = rem_conf.get('exam_minutes_before', 30)
        self.day_before_notify = rem_conf.get('exam_day_before_notify', True)
        logger.info(f"ExamReminder 热重载: 考试提前 {self.minutes_before} 分钟提醒，考前一天通知: {self.day_before_notify}")
    
    def check_and_schedule(self, exam_data, scheduler):
        now = datetime.now()
        for subj in exam_data.subjects:
            if subj.start_time is None or subj.start_time < now:
                continue
                
            exam_id = f'{subj.subject}_{subj.start_time.strftime("%Y%m%d%H%M")}'
            
            job_id_daybefore = f'{exam_id}_daybefore'
            if scheduler.get_job(job_id_daybefore):
                scheduler.remove_job(job_id_daybefore)

            if self.day_before_notify:
                day_before = subj.start_time.replace(hour=20, minute=0) - timedelta(days=1)
                if day_before > now and job_id_daybefore not in self._notified_exams:
                    scheduler.add_job(
                        self._send_exam_reminder,
                        DateTrigger(run_date=day_before),
                        args=[subj, '明天有考试！'],
                        id=job_id_daybefore
                    )
            
            job_id_before = f'{exam_id}_before'
            if scheduler.get_job(job_id_before):
                scheduler.remove_job(job_id_before)

            remind_time = subj.start_time - timedelta(minutes=self.minutes_before)
            if remind_time > now and job_id_before not in self._notified_exams:
                scheduler.add_job(
                    self._send_exam_reminder,
                    DateTrigger(run_date=remind_time),
                    args=[subj, f'{self.minutes_before}分钟后考试！'],
                    id=job_id_before
                )
                
    def _send_exam_reminder(self, subj, msg):
        self.notify_manager.send(
            title=f'📝 考试提醒: {subj.subject}',
            content=f'{msg}\n'
                    f'时间: {subj.time_str}\n'
                    f'地点: {subj.place}\n'
                    f'座位: {subj.seat}'
        )
