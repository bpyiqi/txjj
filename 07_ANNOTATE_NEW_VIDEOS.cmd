@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "datasets\challenge_video_construction\annotation_manifest.json" (
  call windows_bootstrap.cmd --run training\prepare_challenge_videos.py
  if errorlevel 1 pause & exit /b 1
)
echo [INFO] 现有类别：0 吹缆机、1 光缆盘、2 熔接机
echo [INFO] 默认显示167张训练帧；没有目标也要点击保存，形成空标签和人工复核记录。
echo [INFO] 标注台地址：http://127.0.0.1:8765
call windows_bootstrap.cmd --run tools\annotation_server.py --host 127.0.0.1 --port 8765 --dataset datasets\challenge_video_construction
set "EXIT_CODE=%ERRORLEVEL%"
pause
exit /b %EXIT_CODE%
