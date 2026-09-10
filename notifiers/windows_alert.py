# Copyright 2026 XDU Reminder Service
# Windows 原生模态报错弹窗强提醒渠道 (带红叉错误图标 + 提示音 + 置顶)

import sys
import threading
import ctypes
from ctypes import wintypes
from loguru import logger
from notifiers.base import BaseNotifier


class WindowsAlertNotifier(BaseNotifier):
    """Windows 报错模态弹窗强提醒 (支持普通进程与 Windows 服务 Session 0 穿透)"""
    name: str = "windows_alert"

    def __init__(self, timeout: int = 120):
        self.timeout = timeout
        self.supported = sys.platform == "win32"
        if not self.supported:
            logger.debug("当前操作系统非 Windows，windows_alert 强提醒渠道不可用")

    def send(self, title: str, content: str, **kwargs) -> bool:
        """弹出系统模态报错窗口（异步非阻塞执行）"""
        if not self.supported:
            return False

        full_msg = f"{content}\n\n[点击确定关闭提醒 · XDU Reminder]"

        def _popup():
            try:
                # 1. 优先使用 WTSSendMessageW (支持 Windows 服务 Session 0 跨会话穿透到当前用户桌面)
                session_id = ctypes.windll.kernel32.WTSGetActiveConsoleSessionId()
                if session_id != 0xFFFFFFFF:
                    title_bytes = (len(title) + 1) * 2
                    msg_bytes = (len(full_msg) + 1) * 2
                    # 0x10 = MB_ICONERROR, 0x40000 = MB_TOPMOST / MB_SETFOREGROUND
                    style = 0x10 | 0x40000
                    resp = wintypes.DWORD()
                    ok = ctypes.windll.wtsapi32.WTSSendMessageW(
                        0,
                        session_id,
                        title,
                        title_bytes,
                        full_msg,
                        msg_bytes,
                        style,
                        self.timeout,
                        ctypes.byref(resp),
                        False,
                    )
                    if ok:
                        logger.info(f"[WindowsAlert] 弹窗已成功投递至桌面 (Session {session_id})")
                        return True

                # 2. 降级方案：普通 user32 模态弹窗 (适用于普通前台应用)
                # 0x10 = MB_ICONERROR, 0x1000 = MB_SYSTEMMODAL, 0x40000 = MB_SETFOREGROUND
                style = 0x10 | 0x1000 | 0x40000
                ctypes.windll.user32.MessageBoxW(0, full_msg, title, style)
                logger.info("[WindowsAlert] MessageBoxW 模态弹窗已弹出")
                return True
            except Exception as e:
                logger.warning(f"[WindowsAlert] 弹窗触发异常: {e}")
                return False

        # 在独立后台守护线程中运行，绝不阻塞调度器定时引擎
        t = threading.Thread(target=_popup, daemon=True)
        t.start()
        return True

    def test(self) -> bool:
        """发送测试弹窗"""
        return self.send(
            "⚠️ 【XDU Reminder】强提醒报错弹窗测试",
            "恭喜！如果您看到了这个红叉错误弹窗并听到了系统警报音，说明【报错弹窗强提醒】渠道工作完全正常！\n\n上课或考试临近时，系统将通过此弹窗第一时间强行提醒您。"
        )
