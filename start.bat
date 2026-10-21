@echo off
chcp 65001 >nul
cd /d "%~dp0"
python launch_gui.py
if errorlevel 1 (
  echo.
  echo 启动失败。请先安装 Python 3.10+，再运行 install.bat。
  pause
)
