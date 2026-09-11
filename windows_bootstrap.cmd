@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "BOOTSTRAP_ARGS=%*"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import fastapi,uvicorn,multipart,xlsxwriter,reportlab,cv2,torch,ultralytics" >nul 2>nul
  if not errorlevel 1 (
    ".venv\Scripts\python.exe" bootstrap_windows.py %BOOTSTRAP_ARGS%
    exit /b !ERRORLEVEL!
  )
  echo [INFO] Project Python environment is unavailable; looking for a compatible Python...
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
  if not errorlevel 1 (
    py -3.12 bootstrap_windows.py %BOOTSTRAP_ARGS%
    exit /b !ERRORLEVEL!
  )
  py -3.11 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
  if not errorlevel 1 (
    py -3.11 bootstrap_windows.py %BOOTSTRAP_ARGS%
    exit /b !ERRORLEVEL!
  )
)

for /f "delims=" %%P in ('where python 2^>nul') do call :try_python "%%P"
if defined PROJECT_PYTHON (
  "%PROJECT_PYTHON%" bootstrap_windows.py %BOOTSTRAP_ARGS%
  exit /b !ERRORLEVEL!
)

echo [ERROR] Python 3.11 or newer was not found.
echo Install Python 3.11 or 3.12, then run this file again.
exit /b 1

:try_python
if defined PROJECT_PYTHON exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if not errorlevel 1 set "PROJECT_PYTHON=%~1"
exit /b 0
