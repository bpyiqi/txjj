@echo off
setlocal
chcp 65001 >nul
set "EPOCHS=%~1"
if not defined EPOCHS set "EPOCHS=50"
set "MODEL=%~2"
if not defined MODEL set "MODEL=yolov8n.pt"
call windows_bootstrap.cmd --train-safety %EPOCHS% --safety-model %MODEL%
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo [ERROR] Safety supervision model training failed.
) else (
  echo [OK] Safety model generated: backend\models\safety_ppe_yolo.pt
)
pause
exit /b %EXIT_CODE%
