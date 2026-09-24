@echo off
rem 调试启动: 保留控制台以查看报错
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

echo ============================================================
echo  Bader 电荷可视化 - GUI (debug mode)
echo  Python : %PY%
echo  Script : %~dp0bader_gui.py
echo ============================================================
echo.

"%PY%" "%~dp0bader_gui.py"
echo.
echo [exit code] %errorlevel%
pause
