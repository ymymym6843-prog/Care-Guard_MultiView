@echo off
chcp 65001 >nul 2>&1

echo ============================================
echo   CARE-GUARD WAITING AI - Dev Server Start
echo ============================================
echo.

set "PROJECT_DIR=%~dp0.."

set "DEBUG=true"

echo [1/2] Starting Backend...
cd /d "%PROJECT_DIR%\backend"
start "CARE-GUARD-Backend" cmd /k "call venv\Scripts\activate.bat && uvicorn app.main:app --reload --host 0.0.0.0 --port 8001"

ping 127.0.0.1 -n 3 >nul

echo [2/2] Starting Frontend...
cd /d "%PROJECT_DIR%\frontend"
start "CARE-GUARD-Frontend" cmd /k "npm run dev"

ping 127.0.0.1 -n 4 >nul

start http://localhost:5173

echo.
echo ============================================
echo   Servers started!
echo ============================================
echo.
echo   Frontend:  http://localhost:5173
echo   Backend:   http://localhost:8001
echo   API Docs:  http://localhost:8001/docs
echo.
echo   Close terminal windows to stop servers.
echo ============================================
echo.
pause
