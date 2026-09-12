# Copyright 2026 XDU Reminder Service
# 配置加载与管理模块

import os
import sys
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable

import yaml
from loguru import logger

# 默认配置
DEFAULT_CONFIG: dict[str, Any] = {
    "server": {
        "host": "0.0.0.0",
        "port": 5800,
        "secret_key": "",
    },
    "account": {
        "username": "",
        "password": "",
    },
    "reminder": {
        "class_minutes_before": 30,
        "exam_minutes_before": 30,
        "exam_day_before_notify": True,
        "energy_threshold": 100,
        "energy_check_interval_hours": 24.1,
        "energy_max_alerts_per_day": 2,
    },
    "notifiers": {
        "console": {"enabled": True},
        "windows_toast": {"enabled": True},
        "windows_alert": {"enabled": False, "timeout": 120},
        "email": {
            "enabled": False,
            "smtp_host": "smtp.qq.com",
            "smtp_port": 465,
            "smtp_ssl": True,
            "username": "",
            "password": "",
            "to_addr": "",
        },
        "serverchan": {"enabled": False, "key": ""},
        "pushplus": {"enabled": False, "token": ""},
        "qmsg": {"enabled": False, "key": "", "qq": ""},
        "bark": {"enabled": False, "key": "", "server": "https://api.day.app"},
        "dingtalk": {"enabled": False, "webhook": "", "secret": ""},
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并字典，override 覆盖 base"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """应用配置管理器"""

    def __init__(self, config_path: str | Path | None = None, data_dir: str | Path | None = None):
        self._data: dict[str, Any] = {}
        self.config_path: Path | None = None
        self.data_dir: Path
        self._change_listeners: list[Callable[["Config"], None]] = []
        self._last_mtime: float | None = None
        self._watcher_thread: threading.Thread | None = None
        self._watcher_stop: bool = False
        self._lock = threading.Lock()

        # 确定数据目录
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            if getattr(sys, "frozen", False):
                self.data_dir = Path(sys.executable).parent.resolve() / "data"
            else:
                self.data_dir = Path(__file__).parent.parent / "data"

        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 确定配置文件路径（按优先级查找）
        if config_path:
            self.config_path = Path(config_path)
        else:
            if getattr(sys, "frozen", False):
                exe_dir = Path(sys.executable).parent.resolve()
                candidates = [
                    self.data_dir / "config.yaml",
                    exe_dir / "config.yaml",
                ]
            else:
                candidates = [
                    self.data_dir / "config.yaml",
                    Path(__file__).parent.parent / "config.yaml",
                ]
            for candidate in candidates:
                if candidate.exists():
                    self.config_path = candidate
                    break

        self.load()

    def load(self, notify: bool = False) -> None:
        """加载配置文件，与默认配置合并"""
        with self._lock:
            self._data = DEFAULT_CONFIG.copy()

            if self.config_path and self.config_path.exists():
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        file_config = yaml.safe_load(f) or {}
                    self._data = _deep_merge(DEFAULT_CONFIG, file_config)
                    self._last_mtime = os.path.getmtime(self.config_path)
                    logger.info("配置文件已加载: {}", self.config_path)
                except Exception as e:
                    logger.error("配置文件加载失败: {}", e)
            else:
                logger.warning("未找到配置文件，使用默认配置")

            # 自动生成 secret_key
            if not self._data["server"].get("secret_key"):
                self._data["server"]["secret_key"] = secrets.token_hex(32)

        if notify:
            self.notify_change_listeners()

    def save(self, path: Path | None = None) -> None:
        """保存配置到文件"""
        with self._lock:
            save_path = path or self.config_path or (self.data_dir / "config.yaml")
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # 不保存自动生成的 secret_key
            data_to_save = self._data.copy()
            if "server" in data_to_save:
                server = data_to_save["server"].copy()
                server.pop("secret_key", None)
                data_to_save["server"] = server

            with open(save_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    data_to_save,
                    f,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False,
                )

            self.config_path = save_path
            try:
                self._last_mtime = os.path.getmtime(save_path)
            except Exception:
                pass
            logger.info("配置已保存到: {}", save_path)

    def update(self, updates: dict[str, Any]) -> None:
        """更新配置项并保存，随后触发所有热重载监听器"""
        with self._lock:
            self._data = _deep_merge(self._data, updates)
        self.save()
        self.notify_change_listeners()

    def add_change_listener(self, callback: Callable[["Config"], None]) -> None:
        """添加配置更新监听器，用于热重载"""
        if callback not in self._change_listeners:
            self._change_listeners.append(callback)

    def remove_change_listener(self, callback: Callable[["Config"], None]) -> None:
        """移除配置更新监听器"""
        if callback in self._change_listeners:
            self._change_listeners.remove(callback)

    def notify_change_listeners(self) -> None:
        """触发配置更新回调"""
        for cb in list(self._change_listeners):
            try:
                cb(self)
            except Exception as e:
                logger.error("配置变更回调执行失败: {}", e)

    def start_file_watcher(self, interval: float = 2.0) -> None:
        """在后台守护线程中监听配置文件变动，若被外部修改则自动热重载"""
        if self._watcher_thread and self._watcher_thread.is_alive():
            return
        self._watcher_stop = False

        def _watch():
            while not self._watcher_stop:
                time.sleep(interval)
                try:
                    if not self.config_path or not self.config_path.exists():
                        continue
                    current_mtime = os.path.getmtime(self.config_path)
                    if self._last_mtime is not None and current_mtime > self._last_mtime:
                        logger.info("检测到配置文件在外部被修改: {}，正在自动热重载...", self.config_path)
                        self.load(notify=True)
                    elif self._last_mtime is None:
                        self._last_mtime = current_mtime
                except Exception as e:
                    logger.debug("文件变动监听异常: {}", e)

        self._watcher_thread = threading.Thread(target=_watch, daemon=True, name="config-file-watcher")
        self._watcher_thread.start()
        logger.info("配置文件变更监听器已启动 (轮询间隔: {}s)", interval)

    def stop_file_watcher(self) -> None:
        """停止文件变动监听"""
        self._watcher_stop = True

    @property
    def is_configured(self) -> bool:
        """检查是否已完成基本配置（账号密码）"""
        account = self._data.get("account", {})
        return bool(account.get("username")) and bool(account.get("password"))

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        """支持 dot-notation 的取值，如 'account.username'"""
        keys = key.split(".")
        value = self._data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value
