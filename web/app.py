# Copyright 2026 XDU Reminder Service
# Flask Web 管理界面

import sys
import threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from loguru import logger


def create_app(config, ids_session, network_client, notify_manager, scheduler_ref):
    """创建 Flask 应用

    Args:
        config: Config 实例
        ids_session: IDSSession 实例
        network_client: NetworkClient 实例
        notify_manager: NotifyManager 实例
        scheduler_ref: dict，{'scheduler': ReminderScheduler | None}，可动态设置
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = Path(sys._MEIPASS)
        template_dir = base_path / "web" / "templates"
        static_dir = base_path / "web" / "static"
    else:
        template_dir = Path(__file__).parent / "templates"
        static_dir = Path(__file__).parent / "static"

    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir),
    )
    app.secret_key = config["server"]["secret_key"]

    # ─── 状态管理 ───
    # 用于在 IDS 登录过程中，将验证码/MFA 数据传递给 Web 前端
    app_state = {
        "login_status": "idle",  # idle / logging_in / need_captcha / need_mfa / logged_in / error
        "login_step": "",       # 当前登录步骤描述
        "login_error": "",
        "captcha_data": None,   # {big_image: base64, small_image: base64}
        "mfa_info": None,       # {message: str, type: str}
        "mfa_client": None,     # IDSReAuthClient 实例
        "mfa_session": None,    # client 会话
        "mfa_username": None,   # 用户名
        "mfa_service": None,    # target service
        "mfa_type": "sms",      # 'sms' or 'wechat'
        "mfa_result": None,     # {'code': str, 'type': str}
        "mfa_event": threading.Event(),
        "captcha_result": None,  # 用户拖动结果 {move_length: int}
        "captcha_event": threading.Event(),
    }
    app.app_state = app_state

    # 设置 IDS 会话回调
    def on_captcha_needed(captcha_data):
        app_state["captcha_data"] = captcha_data
        app_state["login_status"] = "need_captcha"
        app_state["login_step"] = "需要手动拖动滑块完成拼图验证"
        app_state["captcha_event"].clear()
        try:
            notify_manager.send(
                "🔐 需要手动验证",
                f"滑块验证需要手动完成，请在 Web 界面进行拖动拼图\n"
                f"http://localhost:{config['server']['port']}/captcha"
            )
        except Exception:
            pass
        app_state["captcha_event"].wait(timeout=300)
        return app_state.get("captcha_result")

    def on_mfa_needed(mfa_info):
        app_state["mfa_client"] = mfa_info.get("client")
        app_state["mfa_session"] = mfa_info.get("session")
        app_state["mfa_username"] = mfa_info.get("username")
        app_state["mfa_service"] = mfa_info.get("service")
        app_state["mfa_info"] = mfa_info
        app_state["mfa_type"] = mfa_info.get("type", "sms")
        app_state["mfa_result"] = None
        app_state["login_status"] = "need_mfa"
        app_state["login_step"] = "需要二次认证动态码（请在网页中选择短信或企业微信并获取）"
        app_state["mfa_event"].clear()
        try:
            notify_manager.send(
                "🔐 需要二次认证",
                f"IDS 登录需要二次身份认证，请访问 Web 管理界面选择短信或企业微信并获取动态码：\n"
                f"http://localhost:{config['server']['port']}/mfa"
            )
        except Exception:
            pass
        app_state["mfa_event"].wait(timeout=300)
        return app_state.get("mfa_result")

    def on_step(step_msg):
        app_state["login_step"] = step_msg

    ids_session.on_captcha_needed = on_captcha_needed
    ids_session.on_mfa_needed = on_mfa_needed
    ids_session.on_step = on_step

    def reload_notifiers():
        """根据当前 config 动态重新加载通知管理器"""
        from notifiers import (
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
        notify_manager._notifiers.clear()
        if config.get("notifiers.console.enabled", True):
            notify_manager.add(ConsoleNotifier())
        if config.get("notifiers.windows_toast.enabled", True):
            notify_manager.add(WindowsToastNotifier())
        if config.get("notifiers.windows_alert.enabled", False):
            notify_manager.add(WindowsAlertNotifier(timeout=config.get("notifiers.windows_alert.timeout", 120)))
        if config.get("notifiers.email.enabled", False):
            c = config["notifiers"]["email"]
            notify_manager.add(EmailNotifier(
                smtp_host=c.get("smtp_host", "smtp.qq.com"),
                smtp_port=int(c.get("smtp_port", 465)),
                smtp_ssl=c.get("smtp_ssl", True),
                username=c.get("username", ""),
                password=c.get("password", ""),
                to_addr=c.get("to_addr", ""),
            ))
        if config.get("notifiers.serverchan.enabled", False):
            c = config["notifiers"]["serverchan"]
            if c.get("key"):
                notify_manager.add(ServerChanNotifier(key=c["key"]))
        if config.get("notifiers.pushplus.enabled", False):
            c = config["notifiers"]["pushplus"]
            if c.get("token"):
                notify_manager.add(PushPlusNotifier(token=c["token"]))
        if config.get("notifiers.qmsg.enabled", False):
            c = config["notifiers"]["qmsg"]
            if c.get("key") and c.get("qq"):
                notify_manager.add(QmsgNotifier(key=c["key"], qq=c["qq"]))
        if config.get("notifiers.bark.enabled", False):
            c = config["notifiers"]["bark"]
            if c.get("key"):
                notify_manager.add(BarkNotifier(key=c["key"], server=c.get("server", "https://api.day.app")))
        if config.get("notifiers.dingtalk.enabled", False):
            c = config["notifiers"]["dingtalk"]
            if c.get("webhook"):
                notify_manager.add(DingTalkNotifier(webhook=c["webhook"], secret=c.get("secret", "")))
        logger.info(f"已动态同步并加载 {len(notify_manager._notifiers)} 个通知渠道")

    def reload_all(source_config=None):
        """动态热重载通知渠道与提醒调度器"""
        cfg = source_config or config
        reload_notifiers()
        sched = scheduler_ref.get("scheduler")
        if sched and hasattr(sched, "reload_config"):
            try:
                sched.reload_config(cfg)
            except Exception as e:
                logger.error("调度器热重载失败: {}", e)
        logger.info("所有服务组件已成功完成热重载")

    reload_all()
    if hasattr(config, "add_change_listener"):
        config.add_change_listener(reload_all)

    # ─── 路由 ───

    @app.route("/")
    def index():
        """首页：根据状态重定向"""
        if not config.is_configured:
            return redirect(url_for("setup"))
        if app_state["login_status"] == "need_captcha":
            return redirect(url_for("captcha"))
        if app_state["login_status"] == "need_mfa":
            return redirect(url_for("mfa"))
        return redirect(url_for("status"))

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        """配置向导页"""
        if request.method == "POST":
            # 保存配置
            form = request.form
            updates = {
                "account": {
                    "username": form.get("username", "").strip(),
                    "password": form.get("password", "").strip(),
                },
                "notifiers": {},
            }

            # 解析通知设置
            notifier_types = [
                "console", "windows_toast", "windows_alert", "email", "serverchan",
                "pushplus", "qmsg", "bark", "dingtalk",
            ]
            for nt in notifier_types:
                enabled = form.get(f"{nt}_enabled") == "on"
                notifier_config = {"enabled": enabled}

                if nt == "email":
                    notifier_config.update({
                        "smtp_host": form.get("email_smtp_host", "smtp.qq.com"),
                        "smtp_port": int(form.get("email_smtp_port", "465")),
                        "smtp_ssl": form.get("email_smtp_ssl") == "on",
                        "username": form.get("email_username", ""),
                        "password": form.get("email_password", ""),
                        "to_addr": form.get("email_to_addr", ""),
                    })
                elif nt == "serverchan":
                    notifier_config["key"] = form.get("serverchan_key", "")
                elif nt == "pushplus":
                    notifier_config["token"] = form.get("pushplus_token", "")
                elif nt == "qmsg":
                    notifier_config["key"] = form.get("qmsg_key", "")
                    notifier_config["qq"] = form.get("qmsg_qq", "")
                elif nt == "bark":
                    notifier_config["key"] = form.get("bark_key", "")
                    notifier_config["server"] = form.get("bark_server", "https://api.day.app")
                elif nt == "dingtalk":
                    notifier_config["webhook"] = form.get("dingtalk_webhook", "")
                    notifier_config["secret"] = form.get("dingtalk_secret", "")

                updates["notifiers"][nt] = notifier_config

            # 提醒设置
            updates["reminder"] = {
                "class_minutes_before": int(form.get("class_minutes_before", "30")),
                "exam_minutes_before": int(form.get("exam_minutes_before", "30")),
                "exam_day_before_notify": form.get("exam_day_before_notify") == "on",
                "energy_threshold": float(form.get("energy_threshold", "100")),
                "energy_check_interval_hours": float(form.get("energy_check_interval_hours", "24.1")),
                "energy_max_alerts_per_day": int(form.get("energy_max_alerts_per_day", "2")),
            }

            old_username = str(config.get("account.username", "")).strip()
            old_password = str(config.get("account.password", "")).strip()
            new_username = str(updates["account"]["username"]).strip()
            new_password = str(updates["account"]["password"]).strip()
            account_changed = (new_username != old_username) or (new_password != old_password)
            was_configured = config.is_configured
            is_logged_in = app_state.get("login_status") == "logged_in"

            config.update(updates)
            logger.info("配置已通过 Web 界面更新并完成即时热重载")

            # 若账号密码未变动且当前已成功登录，直接返回状态页（热重载即时生效，不破坏会话）
            if was_configured and is_logged_in and not account_changed:
                return redirect(url_for("status", reloaded="1"))

            # 是否手动滑块验证
            force_manual = form.get("captcha_mode") == "manual"
            return redirect(url_for("do_login", manual="1" if force_manual else "0"))

        return render_template("setup.html", config=config)

    @app.route("/login")
    def do_login():
        """触发后台登录流程"""
        force_manual = request.args.get("manual") == "1"
        if app_state["login_status"] == "logging_in":
            return redirect(url_for("status"))

        app_state["login_status"] = "logging_in"
        app_state["login_step"] = "正在启动登录流程..."
        app_state["login_error"] = ""

        def _login_thread():
            try:
                username = config.get("account.username")
                password = config.get("account.password")
                if not username or not password:
                    app_state["login_status"] = "error"
                    app_state["login_error"] = "账号或密码为空，请在配置页面填写"
                    return

                ids_session.login(username, password, force_manual_captcha=force_manual)
                network_client.save_cookies()

                app_state["login_status"] = "logged_in"
                app_state["login_step"] = "✓ 登录成功！已成功同步登录状态"
                logger.info("IDS 登录成功")

                # 启动调度器
                _start_scheduler()

            except Exception as e:
                logger.error("登录失败: {}", e)
                app_state["login_status"] = "error"
                app_state["login_error"] = str(e)

        thread = threading.Thread(target=_login_thread, daemon=True)
        thread.start()
        return redirect(url_for("status"))

    def _start_scheduler():
        """初始化并启动提醒调度器（若已存在旧实例则先停止）"""
        try:
            old_sched = scheduler_ref.get("scheduler")
            if old_sched and hasattr(old_sched, "stop"):
                try:
                    old_sched.stop()
                except Exception as e:
                    logger.warning("停止旧调度器异常: {}", e)
            from reminder.scheduler import ReminderScheduler
            sched = ReminderScheduler(
                ids_session=ids_session,
                config=config,
                notify_manager=notify_manager,
                data_dir=config.data_dir,
            )
            sched.start()
            scheduler_ref["scheduler"] = sched
            logger.info("提醒调度器已启动")
        except Exception as e:
            logger.error("调度器启动失败: {}", e)

    @app.route("/captcha", methods=["GET"])
    def captcha():
        """滑块验证码页"""
        if app_state["login_status"] != "need_captcha":
            return redirect(url_for("index"))
        return render_template(
            "captcha.html",
            captcha_data=app_state.get("captcha_data", {}),
        )

    @app.route("/captcha/submit", methods=["POST"])
    def captcha_submit():
        """接收滑块验证码拖动结果"""
        data = request.get_json()
        move_length = data.get("move_length", 0)
        app_state["captcha_result"] = {"move_length": move_length}
        app_state["login_status"] = "logging_in"
        app_state["login_step"] = "正在校验滑块拼图结果并继续登录..."
        app_state["captcha_event"].set()
        return jsonify({"status": "ok"})

    @app.route("/mfa", methods=["GET", "POST"])
    def mfa():
        """MFA 验证码输入页"""
        if request.method == "POST":
            code = request.form.get("code", "").strip()
            code_type = request.form.get("type", app_state.get("mfa_type", "sms"))
            if code:
                app_state["mfa_result"] = {"code": code, "type": code_type}
                app_state["login_status"] = "logging_in"
                app_state["login_step"] = "正在提交二次认证动态码并完成登录..."
                app_state["mfa_event"].set()
                return redirect(url_for("status"))
            return render_template(
                "mfa.html",
                mfa_info=app_state.get("mfa_info", {}),
                current_type=app_state.get("mfa_type", "sms"),
                error="请输入验证码",
            )

        if app_state["login_status"] != "need_mfa":
            target_route = "status" if app_state["login_status"] in ("logging_in", "logged_in") else "index"
            return redirect(url_for(target_route))
        return render_template(
            "mfa.html",
            mfa_info=app_state.get("mfa_info", {}),
            current_type=app_state.get("mfa_type", "sms"),
        )

    @app.route("/api/mfa/send-code", methods=["POST"])
    def api_mfa_send_code():
        """重新发送 MFA 动态验证码（支持切换短信与企业微信）"""
        data = request.get_json() or {}
        code_type = data.get("type", "sms")  # 'sms' or 'wechat'
        client = app_state.get("mfa_client")
        session = app_state.get("mfa_session") or ids_session.client
        username = app_state.get("mfa_username", "")
        if not client:
            return jsonify({"status": "error", "message": "当前未处于二次认证等待状态"})
        try:
            delivery_res = client.send_code(session, username or "", code_type=code_type)
            msg = delivery_res.get("returnMessage", "验证码已发送")
            app_state["mfa_type"] = code_type
            if app_state.get("mfa_info"):
                app_state["mfa_info"]["message"] = msg
                app_state["mfa_info"]["type"] = code_type
            channel_name = "手机短信" if code_type == "sms" else "企业微信"
            logger.info(f"MFA 动态码已重新发送 ({channel_name}): {msg}")
            return jsonify({"status": "ok", "message": f"已向您的{channel_name}发送动态码：{msg}", "type": code_type})
        except Exception as e:
            logger.error(f"MFA 发送失败 [{code_type}]: {e}")
            return jsonify({"status": "error", "message": f"发送失败: {e}"})

    @app.route("/api/test-email", methods=["POST"])
    def api_test_email():
        """直接测试当前填写的邮件配置"""
        from notifiers.email_notifier import EmailNotifier
        data = request.get_json() or {}
        smtp_host = data.get("smtp_host", "smtp.qq.com")
        smtp_port = int(data.get("smtp_port", 465))
        smtp_ssl = bool(data.get("smtp_ssl", True))
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        to_addr = data.get("to_addr", "").strip() or username

        if not username or not password:
            return jsonify({"status": "error", "message": "发件邮箱或 SMTP 授权码不能为空"})

        notifier = EmailNotifier(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_ssl=smtp_ssl,
            username=username,
            password=password,
            to_addr=to_addr,
        )
        ok = notifier.send("【XDU Reminder】邮件通知测试成功", "恭喜！您的 QQ 邮箱提醒渠道配置成功。\n\n当西电课表有新课程即将开始（前30分钟）、考试安排临近或宿舍电费余额低于50度时，您将准时在此邮箱收到提醒。")
        if ok:
            return jsonify({"status": "ok", "message": f"测试邮件已成功发送至 {to_addr}！请前往邮箱查收。"})
        else:
            return jsonify({"status": "error", "message": "邮件发送失败，请检查 SMTP 授权码是否正确、是否勾选开启 SSL (端口465)。"})

    def _get_data_summary(sched):
        if sched and hasattr(sched, "get_summary"):
            return sched.get_summary()

        from services.classtable import ClassTableService
        import os, json
        ct_service = ClassTableService(ids_session, str(config.data_dir))
        cached_ct = ct_service.get_cache()
        today_classes = []
        total_courses = 0
        term_start = ""
        semester_code = None
        if cached_ct:
            semester_code = cached_ct.semester_code
            term_start = cached_ct.term_start_day
            total_courses = len(cached_ct.class_details)
            today_classes = ct_service.get_today_classes(cached_ct)

        energy_data = None
        cached_energy = os.path.join(str(config.data_dir), "cache", "energy.json")
        if os.path.exists(cached_energy):
            try:
                with open(cached_energy, "r", encoding="utf-8") as f:
                    ed = json.load(f)
                    energy_data = {
                        "remain": float(ed.get("electricity_remain", 0.0)),
                        "read_date": str(ed.get("last_read_date", "")),
                        "is_low": float(ed.get("electricity_remain", 0.0)) < float(config.get("reminder.energy_threshold", 100)),
                        "cached": True
                    }
            except Exception:
                pass

        return {
            "semester_code": semester_code,
            "term_start_day": term_start,
            "total_courses": total_courses,
            "today_classes": today_classes,
            "energy": energy_data,
            "exams": [],
            "last_sync_time": None,
            "sync_errors": {},
        }

    @app.route("/status")
    def status():
        """运行状态页"""
        sched = scheduler_ref.get("scheduler")
        if app_state["login_status"] == "idle" and sched and getattr(sched, "scheduler", None) and sched.scheduler.running:
            app_state["login_status"] = "logged_in"
            app_state["login_step"] = "✓ 登录成功！已成功同步登录状态"
        summary = _get_data_summary(sched)
        status_data = {
            "login_status": app_state["login_status"],
            "login_step": app_state.get("login_step", ""),
            "login_error": app_state["login_error"],
            "scheduler_running": sched is not None and sched.scheduler.running if sched else False,
            "semester_code": summary.get("semester_code") or (sched.semester_code if sched else None),
            "configured": config.is_configured,
            "summary": summary,
        }
        return render_template("status.html", status=status_data, config=config)

    @app.route("/api/status")
    def api_status():
        """状态 API (JSON)"""
        sched = scheduler_ref.get("scheduler")
        if app_state["login_status"] == "idle" and sched and getattr(sched, "scheduler", None) and sched.scheduler.running:
            app_state["login_status"] = "logged_in"
            app_state["login_step"] = "✓ 登录成功！已成功同步登录状态"
        summary = _get_data_summary(sched)
        return jsonify({
            "login_status": app_state["login_status"],
            "login_step": app_state.get("login_step", ""),
            "login_error": app_state["login_error"],
            "scheduler_running": sched is not None and sched.scheduler.running if sched else False,
            "semester_code": summary.get("semester_code") or (sched.semester_code if sched else None),
            "configured": config.is_configured,
            "summary": summary,
        })

    @app.route("/api/sync-now", methods=["POST"])
    def api_sync_now():
        """手动触发立即同步所有数据（课表、考试、电费）"""
        sched = scheduler_ref.get("scheduler")
        if not sched:
            if app_state["login_status"] == "logged_in":
                _start_scheduler()
                sched = scheduler_ref.get("scheduler")
            if not sched:
                return jsonify({"status": "error", "message": "提醒调度器尚未运行，请确认登录成功"})
        try:
            errors = sched.sync_all()
            summary = sched.get_summary()
            err_msgs = [f"{k}: {v}" for k, v in errors.items()]
            if err_msgs:
                msg = f"同步完成，注意部分告警: {'; '.join(err_msgs)}"
            else:
                msg = "课表与电表数据已成功全部同步！"
            return jsonify({"status": "ok", "message": msg, "summary": summary, "errors": errors})
        except Exception as e:
            logger.error(f"手动同步失败: {e}")
            return jsonify({"status": "error", "message": f"同步失败: {e}"})

    @app.route("/api/test-notify", methods=["POST"])
    def api_test_notify():
        """测试通知渠道"""
        reload_notifiers()
        results = notify_manager.test_all()
        return jsonify(results)

    @app.route("/api/relogin", methods=["POST"])
    def api_relogin():
        """重新登录"""
        network_client.clear_cookies()
        app_state["login_status"] = "idle"
        app_state["login_step"] = ""
        return redirect(url_for("do_login"))

    @app.route("/api/service-status")
    def api_service_status():
        """获取 Windows 系统服务状态"""
        if sys.platform != "win32":
            return jsonify({"supported": False, "installed": False, "running": False, "state": "仅支持 Windows 系统"})
        try:
            import subprocess
            proc = subprocess.run(["sc", "query", "XDUReminder"], capture_output=True, text=True, timeout=3)
            out = proc.stdout
            if "1060" in out or "does not exist" in out:
                return jsonify({"supported": True, "installed": False, "running": False, "state": "未安装"})
            running = "RUNNING" in out or "STATE              : 4" in out
            return jsonify({
                "supported": True,
                "installed": True,
                "running": running,
                "state": "服务运行中" if running else "服务已停止"
            })
        except Exception as e:
            return jsonify({"supported": True, "installed": False, "running": False, "state": "查询异常", "error": str(e)})

    @app.route("/api/install-service", methods=["POST"])
    def api_install_service():
        """通过内置 NSSM 或脚本安装为 Windows 后台服务"""
        if sys.platform != "win32":
            return jsonify({"status": "error", "message": "当前操作系统非 Windows，不支持安装 Windows 服务"})

        import subprocess
        is_frozen = getattr(sys, "frozen", False)
        exe_path = sys.executable if is_frozen else sys.executable
        app_dir = Path(exe_path).parent.resolve() if is_frozen else Path(__file__).parent.parent.resolve()

        # 检查是否具备管理员权限
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            is_admin = False

        if not is_admin:
            bat_path = app_dir / "install_service.bat"
            if bat_path.exists():
                try:
                    import ctypes
                    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(bat_path), "", str(app_dir), 1)
                    if ret > 32:
                        return jsonify({
                            "status": "ok",
                            "elevated": True,
                            "message": "已弹出系统管理员提权窗口，请点击【是】以完成后台服务注册。服务成功启动后配置程序将自动退出。"
                        })
                except Exception as e:
                    logger.warning(f"ShellExecuteW runas failed: {e}")

        nssm_candidates = [
            app_dir / "nssm.exe",
            Path(__file__).parent.parent / "nssm.exe",
            "nssm",
        ]
        nssm_bin = None
        for cand in nssm_candidates:
            if isinstance(cand, Path) and cand.exists():
                nssm_bin = str(cand)
                break
            elif isinstance(cand, str):
                import shutil
                if shutil.which(cand):
                    nssm_bin = cand
                    break

        if not nssm_bin:
            return jsonify({"status": "error", "message": "未找到 nssm.exe 工具，请运行 install_service.bat 手动安装"})

        try:
            # 停止并移除已有服务
            subprocess.run([nssm_bin, "stop", "XDUReminder"], capture_output=True)
            subprocess.run([nssm_bin, "remove", "XDUReminder", "confirm"], capture_output=True)

            # 安装服务
            if is_frozen:
                cmd_args = [nssm_bin, "install", "XDUReminder", str(Path(exe_path).resolve()), "--service"]
            else:
                main_py = str((app_dir / "main.py").resolve())
                cmd_args = [nssm_bin, "install", "XDUReminder", str(Path(exe_path).resolve()), main_py, "--service"]

            subprocess.run(cmd_args, check=True, capture_output=True)
            subprocess.run([nssm_bin, "set", "XDUReminder", "AppDirectory", str(app_dir)], check=True, capture_output=True)
            subprocess.run([nssm_bin, "set", "XDUReminder", "Description", "XDU 校园生活提醒后台服务 (课程/考试/电费)"], check=True, capture_output=True)
            subprocess.run([nssm_bin, "set", "XDUReminder", "Start", "SERVICE_AUTO_START"], check=True, capture_output=True)

            log_dir = app_dir / "data" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run([nssm_bin, "set", "XDUReminder", "AppStdout", str(log_dir / "service_out.log")], check=True, capture_output=True)
            subprocess.run([nssm_bin, "set", "XDUReminder", "AppStderr", str(log_dir / "service_err.log")], check=True, capture_output=True)
            
            # 启动服务
            subprocess.run([nssm_bin, "start", "XDUReminder"], check=True, capture_output=True)
            logger.info("Windows 系统后台服务 XDUReminder 安装并启动成功")
            return jsonify({"status": "ok", "message": "Windows 系统后台服务 XDUReminder 已成功注册并启动！它将在后台开机自启静默守护。"})
        except Exception as e:
            logger.error("服务注册失败: {}", e)
            return jsonify({"status": "error", "message": f"安装服务失败: {e}。如权限不足，请右键管理员运行 install_service.bat。"})

    @app.route("/api/uninstall-service", methods=["POST"])
    def api_uninstall_service():
        """卸载 Windows 系统后台服务"""
        if sys.platform != "win32":
            return jsonify({"status": "error", "message": "非 Windows 平台"})

        import subprocess
        is_frozen = getattr(sys, "frozen", False)
        exe_path = sys.executable if is_frozen else sys.executable
        app_dir = Path(exe_path).parent.resolve() if is_frozen else Path(__file__).parent.parent.resolve()

        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            is_admin = False

        if not is_admin:
            bat_path = app_dir / "uninstall_service.bat"
            if bat_path.exists():
                try:
                    import ctypes
                    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(bat_path), "", str(app_dir), 1)
                    if ret > 32:
                        return jsonify({
                            "status": "ok",
                            "elevated": True,
                            "message": "已弹出系统管理员提权窗口，请点击【是】以完成后台服务卸载。"
                        })
                except Exception as e:
                    logger.warning(f"ShellExecuteW runas failed: {e}")

        nssm_bin = str(app_dir / "nssm.exe") if (app_dir / "nssm.exe").exists() else "nssm"

        try:
            subprocess.run([nssm_bin, "stop", "XDUReminder"], capture_output=True)
            subprocess.run([nssm_bin, "remove", "XDUReminder", "confirm"], capture_output=True)
            logger.info("Windows 服务 XDUReminder 已卸载")
            return jsonify({"status": "ok", "message": "Windows 系统后台服务 XDUReminder 已成功卸载。"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})

    @app.route("/api/exit", methods=["POST"])
    def api_exit():
        """退出当前配置程序进程"""
        logger.info("用户请求退出配置程序，准备退出...")
        def _delayed_exit():
            import time
            import os
            time.sleep(1.0)
            os._exit(0)
        threading.Thread(target=_delayed_exit, daemon=True).start()
        return jsonify({"status": "ok", "message": "配置程序正在安全关闭..."})

    @app.route("/test-captcha")
    def test_captcha():
        """手动打开滑块验证测试界面"""
        import base64
        from auth.slider_captcha import SliderCaptchaSolver
        solver = SliderCaptchaSolver()
        cookie_str = network_client.get_cookie_string("ids.xidian.edu.cn")
        solver.update_puzzle(network_client.ids_client, cookie_str)
        app_state["captcha_data"] = {
            "big_image": base64.b64encode(solver.puzzle_data).decode("utf-8"),
            "small_image": base64.b64encode(solver.piece_data).decode("utf-8"),
        }
        app_state["login_status"] = "need_captcha"
        return redirect(url_for("captcha"))

    return app


def run_web_server(app, host: str = "0.0.0.0", port: int = 5800):
    """在后台线程中启动 Flask Web 服务器"""
    def _run():
        # 使用 Werkzeug 的非 debug 模式
        logger.info("Web 管理界面启动: http://{}:{}", host, port)
        app.run(host=host, port=port, debug=False, use_reloader=False)

    thread = threading.Thread(target=_run, daemon=True, name="web-server")
    thread.start()
    return thread
