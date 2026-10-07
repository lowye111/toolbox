@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.8 或更高版本，安装时勾选 "Add Python to PATH"
    pause
    exit /b 1
)

python "工具菜单.py"
pause