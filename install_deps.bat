@echo off
rem 安装依赖 (chem_env)
setlocal EnableExtensions
cd /d "%~dp0"

set "PY=D:\miniconda3\envs\chem_env\python.exe"
if not exist "%PY%" (
  for %%I in (python.exe) do set "PY=%%~$PATH:I"
)
if not exist "%PY%" (
  echo [ERROR] Python interpreter not found.
  pause
  exit /b 1
)

"%PY%" -m pip install -r "%~dp0requirements.txt"
echo.
echo 如需使用 Playwright 自带 Chromium (系统已有 Edge/Chrome 时可跳过):
echo     "%PY%" -m playwright install chromium
pause
