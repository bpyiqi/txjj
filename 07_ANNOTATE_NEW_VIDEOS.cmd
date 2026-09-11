@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "datasets\challenge_video_construction\annotation_manifest.json" (
  "D:\python312\python.exe" training\prepare_challenge_videos.py
  if errorlevel 1 pause & exit /b 1
)
echo [INFO] 标注台地址：http://127.0.0.1:8765
"D:\python312\python.exe" tools\annotation_server.py --host 127.0.0.1 --port 8765 --dataset datasets\challenge_video_construction
pause
