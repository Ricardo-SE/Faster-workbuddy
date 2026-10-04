@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: 1. 动态嗅探 Python 3 解释器 (优先 py -3，其次系统 python)
set PYTHON_CMD=
set PYTHONW_CMD=

where.exe py >nul 2>&1
if %errorlevel% equ 0 (
    py -3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_CMD=py -3
        set PYTHONW_CMD=pyw -3
    )
)

if "%PYTHON_CMD%"=="" (
    where.exe python >nul 2>&1
    if %errorlevel% equ 0 (
        python -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
        if %errorlevel% equ 0 (
            set PYTHON_CMD=python
            set PYTHONW_CMD=pythonw
        )
    )
)

:: 2. 如果未找到有效 Python 3.8+ 环境，给出白话引导
if "%PYTHON_CMD%"=="" (
    echo ========================================================
    echo  [环境提示] 未检测到可用的 Python 3.8+ 运行环境！
    echo ========================================================
    echo  1. 若您希望运行源码，请从 python.org 安装 Python 3 (勾选 Add to PATH)；
    echo  2. 若您不想配置环境，可直接前往 GitHub Releases 页面下载免安装版 AgentCleaner.exe。
    echo ========================================================
    echo.
    pause
    exit /b 1
)

:: 3. 依赖自愈检测 (customtkinter, psutil)
%PYTHON_CMD% -c "import customtkinter, psutil" >nul 2>&1
if %errorlevel% neq 0 (
    echo ========================================================
    echo  [自愈向导] 首次运行检测：正在为您自动安装必要三方依赖...
    echo ========================================================
    %PYTHON_CMD% -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo.
        echo [错误] 依赖安装失败，请检查网络连接或手动执行: %PYTHON_CMD% -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
    echo  依赖安装完成！正在启动桌面界面...
    timeout /t 1 >nul
)

:: 4. 纯图形静默启动（秒开且无黑框残留）
if not "%PYTHONW_CMD%"=="" (
    start "" %PYTHONW_CMD% "%~dp0app_gui.pyw"
) else (
    start "" "%~dp0app_gui.pyw"
)
exit /b 0
