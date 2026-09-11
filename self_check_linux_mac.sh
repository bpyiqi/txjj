#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m pip install -r backend/requirements.txt
python3 self_check.py
