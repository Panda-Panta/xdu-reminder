# Copyright 2026 XDU Reminder Service
# 主服务入口程序

import argparse
import os
import signal
import sys
import time
from pathlib import Path

from loguru import logger

from core.config import Config
from core.logger import setup_logger
from core.network import NetworkClient, get_ids_client
from auth.ids_session import IDSSession
from notifiers import (
    NotifyManager,
    ConsoleNotifier,
    WindowsToastNotifier,
    WindowsAlertNotifier,
    EmailNotifier,
    ServerChanNotifier,
    PushPlusNotifier,
    QmsgNotifier,
    BarkNotifier,
    DingTalkNotifier,
)
from reminder.scheduler import ReminderScheduler
from web.app import create_app, run_web_server


def setup_notifiers(config: Config) -> NotifyManager:
    """根据配置初始化所有通知渠道"""
    manager = NotifyManager()

    # 控制台
    if config.get("notifiers.console.enabled", True):
        manager.add(ConsoleNotifier())

    # Windows Toast
    if config.get("notifiers.windows_toast.enabled", True):
        manager.add(WindowsToastNotifier())

    # Windows 强提醒报错弹窗
    if config.get("notifiers.windows_alert.enabled", False):
        manager.add(WindowsAlertNotifier(timeout=config.get("notifiers.windows_alert.timeout", 120)))

    # 邮件 (SMTP)
    if config.get("notifiers.email.enabled", False):
        c = config["notifiers"]["email"]
        manager.add(EmailNotifier(
            smtp_host=c.get("smtp_host", "smtp.qq.com"),
            smtp_port=int(c.get("smtp_port", 465)),
            smtp_ssl=c.get("smtp_ssl", True),
            username=c.get("username", ""),
            password=c.get("password", ""),
            to_addr=c.get("to_addr", ""),
        ))

    # Server酱
    if config.get("notifiers.serverchan.enabled", False):
        c = config["notifiers"]["serverchan"]
        if c.get("key"):
            manager.add(ServerChanNotifier(key=c["key"]))

    # PushPlus
    if config.get("notifiers.pushplus.enabled", False):
        c = config["notifiers"]["pushplus"]
        if c.get("token"):
            manager.add(PushPlusNotifier(token=c["token"]))

    # Qmsg酱
    if config.get("notifiers.qmsg.enabled", False):
        c = config["notifiers"]["qmsg"]
        if c.get("key") and c.get("qq"):
            manager.add(QmsgNotifier(key=c["key"], qq=c["qq"]))

    # Bark (iOS)
    if config.get("notifiers.bark.enabled", False):
        c = config["notifiers"]["bark"]
        if c.get("key"):
            manager.add(BarkNotifier(
                key=c["key"],
                server=c.get("server", "https://api.day.app")
            ))

    # 钉钉
    if config.get("notifiers.dingtalk.enabled", False):
        c = config["notifiers"]["dingtalk"]
        if c.get("webhook"):
            manager.add(DingTalkNotifier(
                webhook=c["webhook"],
                secret=c.get("secret", "")
            ))

    return manager


def main():
    parser = argparse.ArgumentParser(description="XDU 校园生活智能提醒后台服务")
    parser.add_argument("--config", "-c", help="指定配置文件路径 (config.yaml)")
    parser.add_argument("--data-dir", "-d", help="指定数据运行目录 (data/)")
    parser.add_argument("--host", default=None, help="Web 管理界面监听地址 (默认 0.0.0.0)")
    parser.add_argument("--port", "-p", type=int, default=None, help="Web 管理界面监听端口 (默认 5800)")
    parser.add_argument("--service", action="store_true", help="以 Windows 后台守护服务模式启动 (不自动弹出网页)")
    parser.add_argument("--setup", action="store_true", help="以首次配置向导模式启动 (自动打开浏览器)")
    parser.add_argument("--no-browser", action="store_true", help="禁用自动在浏览器中打开配置界面")
    parser.add_argument("--debug", action="store_true", help="开启调试日志")
    args = parser.parse_args()

    # 确定路径
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).parent.resolve()
    else:
        base_dir = Path(__file__).parent.resolve()
    data_dir = Path(args.data_dir).resolve() if args.data_dir else (base_dir / "data")
    data_dir.mkdir(parents=True, exist_ok=True)

    # 1. 初始化日志
    setup_logger(data_dir=data_dir, debug=args.debug)
    logger.info("==========================================")
    if args.service:
        logger.info("  XDU Reminder Service 正在以后台服务模式启动...")
    else:
        logger.info("  XDU Reminder Service 正在启动配置管理界面...")
    logger.info("==========================================")

    # 2. 加载配置
    config = Config(config_path=args.config, data_dir=data_dir)
    host = args.host or config.get("server.host", "0.0.0.0")
    port = args.port or config.get("server.port", 5800)

    # 3. 初始化网络客户端与 IDS 统一认证
    network_client = NetworkClient(data_dir)
    ids_session = IDSSession(str(data_dir))

    # 4. 初始化通知渠道
    notify_manager = setup_notifiers(config)

    # 5. 调度器引用对象 (可供 Flask 动态控制)
    scheduler_ref = {"scheduler": None}

    # 6. 启动 Web 管理界面 (后台线程)
    app = create_app(
        config=config,
        ids_session=ids_session,
        network_client=network_client,
        notify_manager=notify_manager,
        scheduler_ref=scheduler_ref,
    )
    run_web_server(app, host=host, port=port)

    # 只要不是服务守护模式且未禁用浏览器，双击或启动后均自动在默认浏览器中打开配置/管理页面
    if not args.service and not args.no_browser:
        import threading
        def _open_browser():
            time.sleep(1.2)
            url = f"http://localhost:{port}" if host == "0.0.0.0" else f"http://{host}:{port}"
            logger.info("正在自动为您在默认浏览器中打开配置管理界面: {}", url)
            try:
                os.startfile(url)
            except Exception:
                try:
                    import webbrowser
                    webbrowser.open(url)
                except Exception:
                    logger.warning("自动打开浏览器失败，请手动在浏览器访问: {}", url)
        threading.Thread(target=_open_browser, daemon=True).start()

    # 7. 若已完成基础配置，尝试自动恢复/建立登录并启动后台调度器
    if config.is_configured:
        logger.info("检测到已有配置，尝试启动后台提醒调度器...")
        try:
            username = config.get("account.username")
            password = config.get("account.password")
            # 验证已有会话或尝试自动登录
            try:
                ids_session.check_and_login(
                    target="https://ehall.xidian.edu.cn/appShow?appId=4770397878132218",
                    username=username,
                    password=password,
                )
            except Exception as e:
                logger.warning("通过现有 Cookie 登录失败，尝试执行完整登录: {}", e)
                ids_session.login(username=username, password=password)

            # 启动定时调度器
            sched = ReminderScheduler(
                ids_session=ids_session,
                config=config,
                notify_manager=notify_manager,
                data_dir=str(data_dir),
            )
            sched.start()
            scheduler_ref["scheduler"] = sched
            if hasattr(app, "app_state"):
                app.app_state["login_status"] = "logged_in"
                app.app_state["login_step"] = "✓ 登录成功！已成功恢复/建立会话"
            logger.info("✓ 提醒服务调度引擎已成功启动！无需保留浏览器界面。")
        except Exception as e:
            if hasattr(app, "app_state"):
                app.app_state["login_status"] = "error"
                app.app_state["login_error"] = str(e)
            logger.error("自动登录与调度器启动失败: {}。请通过 Web 管理界面重新登录验证。", e)
    else:
        logger.info("尚未完成初始化配置。请在浏览器中打开: http://{}:{} 完成设置与登录", "localhost" if host == "0.0.0.0" else host, port)

    # 8. 优雅退出信号监听
    def handle_exit(signum, frame):
        logger.info("接收到终止信号 ({})，正在安全停止后台任务...", signum)
        if scheduler_ref.get("scheduler"):
            try:
                scheduler_ref["scheduler"].stop()
            except Exception as e:
                logger.warning("停止调度器发生异常: {}", e)
        network_client.close()
        logger.info("XDU Reminder Service 已安全退出。")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # 9. 主守护线程保活
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        handle_exit(signal.SIGINT, None)


if __name__ == "__main__":
    main()
