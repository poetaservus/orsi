@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\create_shortcut.ps1" -ApplicationRoot "%~dp0."
if errorlevel 1 (
    echo The O.R.S.I shortcut could not be created.
    pause
    exit /b 1
)
exit /b 0
