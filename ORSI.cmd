@echo off
setlocal
set "ORSI_ROOT=%~dp0"
if /I "%~1"=="skill" goto skill
set "ORSI_PYTHON=%ORSI_ROOT%runtime\python\pythonw.exe"

if not exist "%ORSI_PYTHON%" (
    echo O.R.S.I portable runtime is missing.
    echo Run packaging\build-portable-runtime.ps1 once before copying this folder to the pendrive.
    pause
    exit /b 1
)

cd /d "%ORSI_ROOT%"
set "PATH=%ORSI_ROOT%runtime\python\Lib\site-packages\nvidia\cu13\bin\x86_64;%PATH%"
start "O.R.S.I" "%ORSI_PYTHON%" -m app.main
exit /b 0

:skill
set "ORSI_PYTHON=%ORSI_ROOT%runtime\python\python.exe"
if not exist "%ORSI_PYTHON%" (
    echo O.R.S.I portable console runtime is missing.
    exit /b 1
)
"%ORSI_PYTHON%" "%ORSI_ROOT%app\main.py" %*
exit /b %errorlevel%
