@echo off
title NSE Market Data Pipeline - Windows RDP
echo ============================================================
echo   NSE Market Data Pipeline & Terminal - Windows RDP
echo ============================================================

cd /d "%~dp0..\.."

:: 0. Environment File Check
if not exist ".env" (
    echo [Setup] .env file not found. Creating from .env.example...
    copy ".env.example" ".env"
)

:: 1. Detect Python Executable (py or python)
set PYTHON_BIN=python
py --version >nul 2>&1
if %errorlevel% == 0 (
    set PYTHON_BIN=py
)

echo [1/4] Checking Python virtual environment...
if not exist ".venv\Scripts\activate.bat" (
    echo Virtual environment not found. Creating .venv using %PYTHON_BIN%...
    %PYTHON_BIN% -m venv .venv
    call .venv\Scripts\activate.bat
    echo Installing backend dependencies...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    python -m pip install -e .
) else (
    call .venv\Scripts\activate.bat
)

:: Ensure project is installed in editable mode
set PYTHONPATH=./src;./backend/src

echo [2/4] Initializing Database & MongoDB Auto-Hydration...
python -m nse_pipeline.cli.setup_database
python -c "from nse_pipeline.services.mongo_sync_service import MongoSyncService; MongoSyncService().ensure_sql_hydrated_from_mongo()"

echo [3/4] Launching FastAPI Backend on port 8000...
start "NSE Backend (FastAPI)" cmd /k "call .venv\Scripts\activate.bat && set PYTHONPATH=./src;./backend/src && uvicorn nse_pipeline.api.app:app --host 0.0.0.0 --port 8000"

echo [4/4] Launching Frontend Terminal on port 3000...
cd frontend
if not exist "node_modules" (
    echo Installing frontend dependencies...
    call npm install
)

:: Launch frontend dev server accessible to local and network RDP clients
start "NSE Frontend" cmd /k "npm run dev -- --host 0.0.0.0 --port 3000"

cd ..
echo ============================================================
echo   All NSE Services have been launched successfully!
echo   Frontend UI:  http://localhost:3000
echo   Backend API:  http://localhost:8000/docs
echo   Default Admin: admin@nse.com / admin123
echo ============================================================
pause
