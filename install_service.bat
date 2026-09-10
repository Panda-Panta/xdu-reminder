@echo off
chcp 65001 >nul
echo ====================================================
echo        XDU Reminder Service Windows 服务安装向导
echo ====================================================
echo.

:: 检查管理员权限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 请右键以“管理员身份运行”此脚本！
    pause
    exit /b 1
)

set SERVICE_NAME=XDUReminder
set APP_DIR=%~dp0
cd /d "%APP_DIR%"

:: 检查是否存在编译好的独立可执行文件
set RUN_CMD=
set RUN_ARGS=

if exist "%APP_DIR%xdu-reminder.exe" (
    set RUN_CMD=%APP_DIR%xdu-reminder.exe
    set RUN_ARGS=--service
    echo [信息] 优先使用独立可执行文件: %APP_DIR%xdu-reminder.exe
) else if exist "%APP_DIR%dist\xdu-reminder.exe" (
    set RUN_CMD=%APP_DIR%dist\xdu-reminder.exe
    set RUN_ARGS=--service
    echo [信息] 优先使用独立可执行文件: %APP_DIR%dist\xdu-reminder.exe
) else (
    :: 查找 Python 可执行路径
    set PYTHON_EXE=
    if exist "%APP_DIR%venv\Scripts\python.exe" (
        set PYTHON_EXE=%APP_DIR%venv\Scripts\python.exe
    ) else (
        for /f "delims=" %%i in ('where python 2^>nul') do (
            if not defined PYTHON_EXE set PYTHON_EXE=%%i
        )
    )

    if not defined PYTHON_EXE (
        echo [错误] 未找到编译好的 xdu-reminder.exe，也未在系统 PATH 或本地 venv 中找到 python.exe！
        echo 请先下载或编译 exe 文件，或安装 Python 3.11+。
        pause
        exit /b 1
    )
    set RUN_CMD=%PYTHON_EXE%
    set RUN_ARGS=main.py --service
    echo [信息] 使用 Python 解释器: %PYTHON_EXE% main.py --service
)

echo [信息] 项目工作目录: %APP_DIR%

:: 检查 nssm 是否存在
set NSSM_EXE=
if exist "%APP_DIR%nssm.exe" (
    set NSSM_EXE=%APP_DIR%nssm.exe
) else (
    for /f "delims=" %%i in ('where nssm 2^>nul') do (
        if not defined NSSM_EXE set NSSM_EXE=%%i
    )
)

if not defined NSSM_EXE (
    echo.
    echo [提示] 未检测到 nssm.exe (Windows 服务管理器)
    echo 推荐使用 NSSM 注册为系统服务以获得开机自启和崩溃自动重启支持。
    echo 正在为您下载 NSSM 工具...
    powershell -Command "Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' -OutFile '%APP_DIR%nssm.zip'" >nul 2>&1
    if exist "%APP_DIR%nssm.zip" (
        powershell -Command "Expand-Archive -Path '%APP_DIR%nssm.zip' -DestinationPath '%APP_DIR%nssm_temp' -Force" >nul 2>&1
        copy "%APP_DIR%nssm_temp\nssm-2.24\win64\nssm.exe" "%APP_DIR%nssm.exe" >nul 2>&1
        del "%APP_DIR%nssm.zip" >nul 2>&1
        rd /s /q "%APP_DIR%nssm_temp" >nul 2>&1
        set NSSM_EXE=%APP_DIR%nssm.exe
    )
)

if defined NSSM_EXE (
    echo [信息] 正在通过 NSSM 注册服务 %SERVICE_NAME%...
    "%NSSM_EXE%" stop %SERVICE_NAME% >nul 2>&1
    "%NSSM_EXE%" remove %SERVICE_NAME% confirm >nul 2>&1
    "%NSSM_EXE%" install %SERVICE_NAME% "%RUN_CMD%" %RUN_ARGS%
    "%NSSM_EXE%" set %SERVICE_NAME% AppDirectory "%APP_DIR%"
    "%NSSM_EXE%" set %SERVICE_NAME% Description "XDU 校园生活提醒后台服务 (课程/考试/电费)"
    "%NSSM_EXE%" set %SERVICE_NAME% Start SERVICE_AUTO_START
    "%NSSM_EXE%" set %SERVICE_NAME% AppStdout "%APP_DIR%data\logs\service_out.log"
    "%NSSM_EXE%" set %SERVICE_NAME% AppStderr "%APP_DIR%data\logs\service_err.log"
    "%NSSM_EXE%" start %SERVICE_NAME%
    echo.
    echo [成功] 服务 %SERVICE_NAME% 已注册并启动成功！
) else (
    echo [警告] 未能自动获取 NSSM，将创建开机启动批处理或快捷方式。
    echo 您也可以直接运行: python main.py 启动服务。
)

echo.
echo ====================================================
echo 现在服务已在后台静默运行！
echo 请在浏览器中打开: http://localhost:5800 完成初次配置与登录。
echo 配置完成后即可关闭网页，提醒服务将在后台常驻。
echo ====================================================
echo.
pause
