@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call windows_bootstrap.cmd --run training\freeze_challenge_dataset.py
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo [ERROR] 数据集未冻结，请完成167张施工框标注和116张安全事件人工真值。
) else (
  echo [OK] 167张施工框、116张安全事件真值及数据划分哈希已冻结。
)
pause
exit /b %EXIT_CODE%
