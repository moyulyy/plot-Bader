@echo off
rem 命令行: 用 test 例子生成 outputs/bader.gif
setlocal EnableExtensions
cd /d "%~dp0"

set "PY=D:\miniconda3\envs\chem_env\python.exe"
if not exist "%PY%" (
  for %%I in (python.exe) do set "PY=%%~$PATH:I"
)

"%PY%" "%~dp0bader_to_gif.py" ^
  --poscar "test\POSCAR" --acf "test\ACF.dat" ^
  --out "outputs\bader.gif" --html "outputs\bader.html" ^
  --label charge --color element --view front --rot-axis c ^
  --rot-angle 360 --frames 60 --fps 20 -w 640

echo.
pause
