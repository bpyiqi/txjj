@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call windows_bootstrap.cmd --run training\validate_challenge_labels.py
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo [ERROR] 标注尚未完成或存在格式错误。
) else (
  echo [OK] 167张施工训练帧已全部人工复核，可以抽查后冻结。
)
pause
exit /b %EXIT_CODE%
