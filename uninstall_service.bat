@echo off
chcp 65001 >nul
echo ====================================================
echo        XDU Reminder Service Windows 服务卸载向导
echo ====================================================
echo.

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 请右键以“管理员身份运行”此脚本！
    pause
    exit /b 1
)

set SERVICE_NAME=XDUReminder
set APP_DIR=%~dp0
set NSSM_EXE=%APP_DIR%nssm.exe

if exist "%NSSM_EXE%" (
    echo [信息] 正在停止并移除服务 %SERVICE_NAME%...
    "%NSSM_EXE%" stop %SERVICE_NAME%
    "%NSSM_EXE%" remove %SERVICE_NAME% confirm
    echo [成功] 服务 %SERVICE_NAME% 已被卸载！
) else (
    sc stop %SERVICE_NAME% >nul 2>&1
    sc delete %SERVICE_NAME% >nul 2>&1
    echo [信息] 已尝试通过系统 sc 命令移除服务 %SERVICE_NAME%。
)

echo.
pause
