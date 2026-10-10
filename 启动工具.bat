@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto nopython

python "工具菜单.py"
if errorlevel 1 pause
exit /b 0

:nopython
echo [ERROR] Python not found. Install Python 3.8+ and check "Add Python to PATH".
pause
exit /b 1
