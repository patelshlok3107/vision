@echo off
cd /d "%~dp0"
echo Stopping VISION...
docker-compose down 2>nul
if errorlevel 1 docker compose down
echo Closing Backend/Frontend windows...
taskkill /FI "WindowTitle eq VISION Backend*" /T /F >nul 2>&1
taskkill /FI "WindowTitle eq VISION Frontend*" /T /F >nul 2>&1
echo Done.
pause
