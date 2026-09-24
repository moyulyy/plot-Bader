@echo off
rem Bader 电荷可视化工作台 - GUI 启动器 (无控制台窗口)
setlocal EnableExtensions
cd /d "%~dp0"

set "SCRIPT=%~dp0bader_gui.py"
set "PY=D:\miniconda3\envs\chem_env\python.exe"

if not exist "%SCRIPT%" (
  echo [ERROR] bader_gui.py not found in %~dp0
  pause
  exit /b 1
)
if not exist "%PY%" (
  for %%I in (python.exe) do set "PY=%%~$PATH:I"
)
if not exist "%PY%" (
  echo [ERROR] Python interpreter not found.
  echo         Expected: D:\miniconda3\envs\chem_env\python.exe
  pause
  exit /b 1
)

set "PYW=%PY:python.exe=pythonw.exe%"
if not exist "%PYW%" set "PYW=%PY%"

start "" "%PYW%" "%SCRIPT%"
exit /b 0
