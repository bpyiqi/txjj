@echo off
setlocal
rem Keep existing uploads and analysis results when opening the shared website.
call "%~dp0windows_bootstrap.cmd" --host 0.0.0.0
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" echo [ERROR] System stopped with code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%
