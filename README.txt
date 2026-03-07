=====================================================
PUB REAL-TIME DEMAND DASHBOARD - SETUP GUIDE
=====================================================

PREREQUISITES:
1. Python 3.10 or higher installed.
2. "Add Python to PATH" checked during installation.

STEP 1: INITIAL SETUP
Double-click 'setup_env.bat'. 
This will:
- Unlock script running on Windows.
- Create the 'venv' folder.
- Install FastAPI, Streamlit, Pandas, etc.

STEP 2: DATA CHECK
Ensure your CSV file is located at:
\cleaner\processed_.csv_file\PUB_Demand_****P.csv

STEP 3: RUNNING THE SYSTEM (LAPTOP 1)
Run 'start_laptop1.bat'. 
This starts:
- The FastAPI Server (app.py)
- The Sender Script (sender.py)

STEP 4: VIEWING THE DASHBOARD (LAPTOP 1 or 2)
Run 'start_laptop2.bat'.
This starts the Streamlit UI.

TROUBLESHOOTING:
- If the sender says 'FileNotFound', check if the CSV filename 
  matches the one in client/sender.py.
- If running on two different laptops, change the SERVER_IP 
  in dashboard/dashboard.py to Laptop 1's local IP.

