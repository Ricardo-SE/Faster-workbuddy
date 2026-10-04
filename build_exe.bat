@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo   Agent Cleaner 独立便携免安装版打包工具 (PyInstaller)
echo ========================================================
echo.

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

echo 正在使用 %PYTHON_CMD% 编译打包为单文件 exe...
echo （自动内嵌 customtkinter 现代组件与 config.json 默认配置）...
echo.

%PYTHON_CMD% -m PyInstaller --noconfirm --clean --onefile --windowed --name "AgentCleaner" --add-data "config.json;." --collect-all customtkinter app_gui.py

if %errorlevel% equ 0 (
    echo.
    echo ========================================================
    echo  打包成功！独立可执行文件位于: dist\AgentCleaner.exe
    echo  可直接将该 exe 挂载至 GitHub Releases 供用户下载使用！
    echo ========================================================
) else (
    echo.
    echo [错误] 打包失败，请检查上方日志。
)

echo.
pause
