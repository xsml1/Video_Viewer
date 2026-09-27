@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify_clean_windows.ps1"
set "test_exit=%ERRORLEVEL%"
echo.
if not "%test_exit%"=="0" echo Self-test failed. Copy the full window output and send it back.
pause
exit /b %test_exit%
