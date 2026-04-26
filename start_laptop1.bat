@echo off
:: Set script to run from the folder it is located in
cd /D "%~dp0"

:: 1. Verify VENV exists before starting
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found at: %~dp0venv
    echo Please run 'setup_env.bat' first.
    pause
    exit /b 1
)

:: 2. Activate VENV using double quotes to handle spaces in path (e.g., "IT BD")
call "venv\Scripts\activate.bat"

:: 3. Clear port 8000 if it is already in use (Prevents "Address already in use" errors)
echo Clearing port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo Starting FastAPI server...
:: Added --reload so code changes apply without restarting the server
start "FASTAPI" cmd /k "uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload"


echo Starting sender...
start "SENDER" cmd /k "python client/sender.py"

echo All systems running.
pause