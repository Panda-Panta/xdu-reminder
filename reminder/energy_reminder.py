from datetime import date
from loguru import logger

class EnergyReminder:
    def __init__(self, notify_manager, config):
        self.notify_manager = notify_manager
        self.config = config
        rem_conf = config.get('reminder', {})
        self.threshold = float(rem_conf.get('energy_threshold', 100))
        self.max_alerts_per_day = int(rem_conf.get('energy_max_alerts_per_day', 2))
        self._last_alert_date = None
        self._alert_count_today = 0

    def reload_config(self, config=None):
        """热重载电费提醒配置"""
        if config is not None:
            self.config = config
        rem_conf = self.config.get('reminder', {})
        self.threshold = float(rem_conf.get('energy_threshold', 100))
        self.max_alerts_per_day = int(rem_conf.get('energy_max_alerts_per_day', 2))
        logger.info(f"EnergyReminder 热重载: 报警阈值更新为 {self.threshold} 度，每日最多提醒 {self.max_alerts_per_day} 次")
    
    def check(self, energy_info):
        if energy_info.electricity_remain < self.threshold:
            if self._should_alert():
                self.notify_manager.send(
                    title='⚡ 电费余额不足',
                    content=f'当前剩余: {energy_info.electricity_remain:.1f} 度\n'
                            f'低于阈值: {self.threshold} 度\n'
                            f'请及时充值！'
                )
                self._record_alert()
    
    def _should_alert(self):
        today = date.today()
        if self._last_alert_date != today:
            self._last_alert_date = today
            self._alert_count_today = 0
        return self._alert_count_today < self.max_alerts_per_day
    
    def _record_alert(self):
        self._alert_count_today += 1
