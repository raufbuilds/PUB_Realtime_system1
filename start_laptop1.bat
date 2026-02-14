@echo off
cd /D "%~dp0"
CALL "%UserProfile%\miniconda3\Scripts\activate.bat" rest_project
call venv\Scripts\activate

echo Starting FastAPI server...
start "FASTAPI" cmd /k "uvicorn server.app:app --host 0.0.0.0 --port 8000"

timeout /t 4 > nul

echo Starting sender...
start "SENDER" cmd /k "python client/sender.py"

pause
