@echo off
setlocal
chcp 65001 >nul
set "EPOCHS=%~1"
if not defined EPOCHS set "EPOCHS=50"
call "%~dp0windows_bootstrap.cmd" --train-safety %EPOCHS%
if errorlevel 1 (
  echo [ERROR] Safety supervision model training failed.
) else (
  echo [OK] Safety model generated: backend\models\safety_ppe_yolo.pt
)
pause
