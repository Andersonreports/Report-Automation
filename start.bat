@echo off
REM ─────────────────────────────────────────────────────────
REM  Anderson Report Automation – Windows Startup Script
REM  Runs the FastAPI server directly (no Docker required)
REM ─────────────────────────────────────────────────────────

cd /d "%~dp0backend"

REM Check if virtual environment exists, create if not
if not exist ".venv" (
    echo [SETUP] Creating virtual environment...
    python -m venv .venv
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Install / update dependencies
echo [SETUP] Installing dependencies...
pip install -r requirements.txt --quiet

REM Create runtime directories
if not exist "reports"              mkdir reports
if not exist "reports-pgta"         mkdir reports-pgta
if not exist "reports-nipt"         mkdir reports-nipt
if not exist "temp"                 mkdir temp
if not exist "drafts\TERA"          mkdir drafts\TERA
if not exist "drafts\PGTA"          mkdir drafts\PGTA
if not exist "drafts\NIPT"          mkdir drafts\NIPT
if not exist "uploads\pgta_cnv"     mkdir uploads\pgta_cnv

REM Copy .env if it doesn't exist yet
if not exist ".env" (
    if exist "..\\.env" copy "..\\.env" ".env" >nul
)

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo  Anderson Report Automation
echo  Server starting at http://localhost:8000
echo  Press Ctrl+C to stop
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

REM Open browser after 3-second delay (runs in background so server can start)
start /B cmd /C "timeout /t 3 /nobreak >nul && start http://localhost:8000"

uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
