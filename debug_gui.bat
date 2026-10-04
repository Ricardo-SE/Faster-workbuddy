@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 正在动态检测 Python 环境并以调试模式启动 Agent Cleaner...

set PYTHON_CMD=
where.exe py >nul 2>&1
if %errorlevel% equ 0 (
    py -3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_CMD=py -3
    )
)

if "%PYTHON_CMD%"=="" (
    set PYTHON_CMD=python
)

%PYTHON_CMD% "app_gui.py"
echo.
echo 界面已关闭。若有报错信息如上所示。
pause
