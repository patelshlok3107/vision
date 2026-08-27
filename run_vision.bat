@echo off
setlocal enabledelayedexpansion
title VISION Launcher
color 0A
cd /d "%~dp0"
echo ==================================================
echo   VISION - One-Click Launcher
echo   Backend: http://127.0.0.1:8000/admin/
echo   Frontend: http://localhost:3000
echo   Login: shlokpatel2599@gmail.com / shlok123
echo ==================================================
echo.

:: Check Docker
docker --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker not found. Install Docker Desktop first.
  pause
  exit /b 1
)

:: Check Ollama
ollama --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Ollama not found. Install from https://ollama.com
  pause
  exit /b 1
)

:: Check Node
node --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Node.js not found. Install Node 18+
  pause
  exit /b 1
)

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.11+
  pause
  exit /b 1
)

echo [1/6] Starting Docker (DB + Redis + Ollama)...
docker-compose up -d db redis ollama 2>nul
if errorlevel 1 docker compose up -d db redis ollama
echo Waiting 12s for DB/Redis/Ollama health...
timeout /t 12 /nobreak >nul
docker ps
echo.

echo [2/6] Pulling Ollama models (first time ~5GB, cached after)...
set OLLAMA_HOST=http://localhost:11434
ollama list | findstr /C:"llama3" >nul || ollama pull llama3
ollama list | findstr /C:"moondream" >nul || ollama pull moondream
ollama list | findstr /C:"nomic-embed" >nul || ollama pull nomic-embed-text
ollama list | findstr /C:"qwen2:0.5b" >nul || ollama pull qwen2:0.5b
echo Models ready.
echo.

echo [3/6] Setting up Backend...
cd backend
if not exist env (
  echo Creating venv...
  python -m venv env
)
if not exist env\Scripts\python.exe (
  echo [ERROR] venv failed
  pause
  exit /b 1
)
echo Installing Python deps (skip if already installed)...
env\Scripts\python.exe -m pip install --quiet --upgrade pip >nul 2>&1
env\Scripts\python.exe -m pip install --quiet django djangorestframework psycopg2-binary pgvector celery redis python-dotenv djangorestframework-simplejwt django-cors-headers channels daphne python-decouple >nul 2>&1

if not exist .env (
  if exist .env.example copy /Y .env.example .env >nul
)

echo Running migrations...
env\Scripts\python.exe manage.py migrate --noinput

echo Updating admin user shlokpatel2599@gmail.com / shlok123...
env\Scripts\python.exe manage.py shell -c "from users.models import User; u, c = User.objects.get_or_create(email='shlokpatel2599@gmail.com', defaults={'username':'shlok'}); u.set_password('shlok123'); u.is_staff=True; u.is_superuser=True; u.username='shlok'; u.save(); print('OK '+u.email)"

echo Warming models (keep_alive 2h)...
env\Scripts\python.exe -c "import requests; [requests.post('http://localhost:11434/api/chat', json={'model':m,'messages':[{'role':'user','content':'Hi'}],'stream':False,'keep_alive':'2h','options':{'num_predict':1}}, timeout=30) for m in ['llama3','qwen2:0.5b']]; print('warmed')" >nul 2>&1

cd ..

echo.
echo [4/6] Setting up Frontend...
cd frontend
if not exist node_modules (
  echo Installing npm deps (first time, 1-2 min)...
  call npm install
) else (
  echo node_modules exists, skipping npm install
)
cd ..

echo.
echo [5/6] Starting Backend + Frontend...
echo Starting Backend on http://127.0.0.1:8000 ...
start "VISION Backend" cmd /k "cd /d %~dp0backend && env\Scripts\python.exe manage.py runserver 0.0.0.0:8000"
timeout /t 4 /nobreak >nul

echo Starting Frontend on http://localhost:3000 ...
start "VISION Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo [6/6] Opening browser...
timeout /t 5 /nobreak >nul
start http://localhost:3000
start http://127.0.0.1:8000/admin/

echo.
echo ==================================================
echo   VISION is running!
echo   Frontend: http://localhost:3000
echo   Backend:  http://127.0.0.1:8000/admin/  (shlokpatel2599@gmail.com / shlok123)
echo   Health:   http://127.0.0.1:8000/api/ai/health/
echo.
echo   Keep the two black windows open.
echo   Close them or run stop_vision.bat to stop.
echo ==================================================
pause
