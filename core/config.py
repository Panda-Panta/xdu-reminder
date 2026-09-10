# Copyright 2026 XDU Reminder Service
# 配置加载与管理模块

import os
import sys
import secrets
from pathlib import Path
from typing import Any

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
        "energy_threshold": 50,
        "energy_check_interval_hours": 4,
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

    def load(self) -> None:
        """加载配置文件，与默认配置合并"""
        self._data = DEFAULT_CONFIG.copy()

        if self.config_path and self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    file_config = yaml.safe_load(f) or {}
                self._data = _deep_merge(DEFAULT_CONFIG, file_config)
                logger.info("配置文件已加载: {}", self.config_path)
            except Exception as e:
                logger.error("配置文件加载失败: {}", e)
        else:
            logger.warning("未找到配置文件，使用默认配置")

        # 自动生成 secret_key
        if not self._data["server"].get("secret_key"):
            self._data["server"]["secret_key"] = secrets.token_hex(32)

    def save(self, path: Path | None = None) -> None:
        """保存配置到文件"""
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
        logger.info("配置已保存到: {}", save_path)

    def update(self, updates: dict[str, Any]) -> None:
        """更新配置项并保存"""
        self._data = _deep_merge(self._data, updates)
        self.save()

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
