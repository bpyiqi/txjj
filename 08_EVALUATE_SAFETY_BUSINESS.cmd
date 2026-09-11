@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call windows_bootstrap.cmd --run training\evaluate_safety_business.py
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo [ERROR] 业务评测未完成，请根据上方信息补齐人工真值或模型权重。
) else (
  echo [OK] 业务评测文件已生成到 evaluation_results。
)
pause
exit /b %EXIT_CODE%
