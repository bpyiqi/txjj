@echo off
setlocal
set "EPOCHS=%~1"
if not defined EPOCHS set "EPOCHS=40"
call "%~dp0windows_bootstrap.cmd" --train %EPOCHS%
if errorlevel 1 (
  echo [ERROR] 模型训练失败。
) else (
  echo [OK] 模型已生成：backend\models\construction_yolo.pt
)
pause
