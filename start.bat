@echo off
title IMMOCORE - Neustart
cd /d "%~dp0"

echo [1/3] Stoppe laufende Container...
docker compose down

echo [2/3] Starte alle Services...
docker compose up -d --build

echo [3/3] Warte auf Backend...
timeout /t 10 /nobreak >nul

echo.
echo ============================================
echo  IMMOCORE gestartet
echo  Frontend : http://localhost:3000
echo  Backend  : http://localhost:8001
echo  API Docs : http://localhost:8001/api/docs/
echo ============================================
echo.

docker compose logs --tail=20 backend

pause
