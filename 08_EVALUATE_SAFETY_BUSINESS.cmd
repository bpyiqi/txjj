@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
"D:\python312\python.exe" training\evaluate_safety_business.py
if errorlevel 1 (
  echo [ERROR] 业务评测未完成，请根据上方信息补齐人工真值或模型权重。
) else (
  echo [OK] 业务评测文件已生成到 evaluation_results。
)
pause
