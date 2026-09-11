@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
"D:\python312\python.exe" training\freeze_challenge_dataset.py
if errorlevel 1 (
  echo [ERROR] 数据集未冻结，请先完成全部283张人工复核。
) else (
  echo [OK] 数据划分与人工真值哈希已冻结。
)
pause
