@echo off
setlocal
cd /d "%~dp0"
if not exist "datasets\expanded_construction\annotation_manifest.json" (
  echo [INFO] Preparing expanded dataset...
  ".venv\Scripts\python.exe" training\prepare_expanded_dataset.py
  if errorlevel 1 (
    echo [ERROR] Dataset preparation failed.
    pause
    exit /b 1
  )
)
echo [INFO] Annotation server will run at http://127.0.0.1:8765
echo [INFO] Keep this window open while annotating.
".venv\Scripts\python.exe" tools\annotation_server.py --host 127.0.0.1 --port 8765
pause
