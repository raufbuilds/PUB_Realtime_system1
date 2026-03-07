@echo off
echo ----------------------------------------------
echo Setting up PUB Realtime System Environment...
echo ----------------------------------------------

:: Fix PowerShell execution policy for the current user
powershell -Command "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser"

:: Create virtual environment if it doesn't exist
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
) else (
    echo venv already exists. skipping...
)

:: Activate and install requirements
echo Installing dependencies from requirements.txt...
call venv\Scripts\activate && pip install -r requirements.txt

echo ----------------------------------------------
echo SETUP COMPLETE!
echo You can now run your start_laptop scripts.
echo ----------------------------------------------
pause