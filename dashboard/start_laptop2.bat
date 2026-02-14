@echo off
cd /D "%~dp0"

call venv\Scripts\activate

echo Starting dashboard...
streamlit run dashboard.py

pause
