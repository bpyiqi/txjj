@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
"D:\python312\python.exe" training\build_release_evidence.py
if errorlevel 1 (
  echo [ERROR] 参赛证据归档失败。
) else (
  echo [OK] 已生成 release_evidence 和 release_evidence.zip。
  echo [INFO] 请检查 data_manifest\missing_items.json，缺项不会被伪造补齐。
)
pause
