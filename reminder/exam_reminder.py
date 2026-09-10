from datetime import datetime, timedelta
from apscheduler.triggers.date import DateTrigger
from loguru import logger

class ExamReminder:
    def __init__(self, notify_manager, config):
        self.notify_manager = notify_manager
        rem_conf = config.get('reminder', {})
        self.minutes_before = rem_conf.get('exam_minutes_before', 30)
        self.day_before_notify = rem_conf.get('exam_day_before_notify', True)
        self._notified_exams = set()
    
    def check_and_schedule(self, exam_data, scheduler):
        now = datetime.now()
        for subj in exam_data.subjects:
            if subj.start_time is None or subj.start_time < now:
                continue
                
            exam_id = f'{subj.subject}_{subj.start_time.strftime("%Y%m%d%H%M")}'
            
            if self.day_before_notify:
                day_before = subj.start_time.replace(hour=20, minute=0) - timedelta(days=1)
                job_id = f'{exam_id}_daybefore'
                if day_before > now and job_id not in self._notified_exams and not scheduler.get_job(job_id):
                    scheduler.add_job(
                        self._send_exam_reminder,
                        DateTrigger(run_date=day_before),
                        args=[subj, '明天有考试！'],
                        id=job_id
                    )
            
            remind_time = subj.start_time - timedelta(minutes=self.minutes_before)
            job_id_before = f'{exam_id}_before'
            if remind_time > now and job_id_before not in self._notified_exams and not scheduler.get_job(job_id_before):
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
