@echo off
setlocal
call "%~dp0windows_bootstrap.cmd"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" echo [ERROR] System stopped with code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%
