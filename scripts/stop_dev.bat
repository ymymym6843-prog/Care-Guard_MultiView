@echo off
echo ============================================
echo   CARE-GUARD - Stop Dev Servers
echo ============================================
echo.

taskkill /f /fi "WINDOWTITLE eq CARE-GUARD-Backend" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq CARE-GUARD-Frontend" >nul 2>&1

echo   All servers stopped.
echo.
pause
