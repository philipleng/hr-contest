@echo off
title HR Backend (FastAPI :8000)

cd /d "%~dp0backend"

if not exist venv (
    echo [ERROR] venv not found. Run: py -3.13 -m venv venv ^&^& venv\Scripts\python -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting FastAPI ...  Docs: http://localhost:8000/docs
rem --proxy-headers / --forwarded-allow-ips: only X-Forwarded-For coming from this machine
rem (Nginx deployed on the same host) is trusted. Otherwise rate limiting would see only
rem Nginx's IP, or clients could spoof the header and bypass the limit.
rem If the backend runs in Docker/K8s, replace 127.0.0.1 with the real gateway IP (e.g. 172.17.0.1).
rem In production prefer --host 127.0.0.1 so only Nginx can reach it and cannot be bypassed.
venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --proxy-headers --forwarded-allow-ips 127.0.0.1
pause
