@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call windows_bootstrap.cmd --run training\build_release_evidence.py
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo [ERROR] 参赛证据归档失败。
) else (
  echo [OK] 已生成 release_evidence 和 release_evidence.zip。
  echo [INFO] 请检查 data_manifest\missing_items.json，缺项不会被伪造补齐。
)
pause
exit /b %EXIT_CODE%
