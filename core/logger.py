# Copyright 2026 XDU Reminder Service
# 日志配置模块

import sys
from pathlib import Path
from loguru import logger


def setup_logger(data_dir: str | Path, debug: bool = False) -> None:
    """初始化 loguru 日志系统

    Args:
        data_dir: 数据目录，日志文件保存在 data_dir/logs/
        debug: 是否开启 DEBUG 级别输出
    """
    log_dir = Path(data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # 移除默认处理器
    logger.remove()

    # 控制台输出
    log_level = "DEBUG" if debug else "INFO"
    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 文件输出 — 按天轮转，保留 30 天
    logger.add(
        str(log_dir / "xdu-reminder-{time:YYYY-MM-DD}.log"),
        level="DEBUG",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
        rotation="00:00",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
    )

    logger.info("日志系统初始化完成, 日志目录: {}", log_dir)
