@echo off
chcp 65001 >nul
cd /d "%~dp0"

set TARGET=%1
if "%TARGET%"=="" set TARGET=WorkBuddy

echo ==================================================
echo   启动清理探针: %TARGET%
echo ==================================================

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

%PYTHON_CMD% "%~dp0clean_core.py" %TARGET%

echo.
pause
