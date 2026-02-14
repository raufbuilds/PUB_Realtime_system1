@echo off
echo =====================================
echo   PUB Realtime System - First Setup
echo =====================================

python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b
)

echo Creating virtual environment...
python -m venv venv

echo Activating virtual environment...
call venv\Scripts\activate

echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt

echo -------------------------------------
echo Setup complete.
echo -------------------------------------
echo Use start_laptop1.bat or start_laptop2.bat to run.
pause
