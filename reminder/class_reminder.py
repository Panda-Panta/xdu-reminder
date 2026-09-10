from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta
from loguru import logger
from services.classtable import ClassTableService

class ClassReminder:
    def __init__(self, notify_manager, config):
        self.notify_manager = notify_manager
        self.minutes_before = config.get('reminder', {}).get('class_minutes_before', 30)
    
    def get_today_reminders(self, classtable_data, scheduler):
        try:
            from services.classtable import ClassTableService
            service = ClassTableService(None, '')
            today_classes = service.get_today_classes(classtable_data)
            
            now = datetime.now()
            today_str = now.strftime('%Y-%m-%d')
            
            for cls in today_classes:
                start_time_str = cls['start_time']
                dt_str = f"{today_str} {start_time_str}"
                class_dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M')
                
                remind_time = class_dt - timedelta(minutes=self.minutes_before)
                if remind_time > now:
                    job_id = f'class_remind_{cls["period_start"]}'
                    if not scheduler.get_job(job_id):
                        scheduler.add_job(
                            self._send_class_reminder, 
                            DateTrigger(run_date=remind_time),
                            args=[cls],
                            id=job_id
                        )
        except Exception as e:
            logger.error(f"调度今日课程失败: {e}")
    
    def _send_class_reminder(self, cls):
        self.notify_manager.send(
            title=f'📚 课程提醒: {cls["name"]}',
            content=f'{self.minutes_before}分钟后上课\n'
                    f'时间: {cls["start_time"]}-{cls["end_time"]}\n'
                    f'地点: {cls["classroom"]}\n'
                    f'老师: {cls["teacher"]}'
        )
