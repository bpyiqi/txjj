#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -c "import fastapi,uvicorn,xlsxwriter,reportlab" >/dev/null 2>&1 || python3 -m pip install -r backend/requirements.txt
python3 run.py --reset
