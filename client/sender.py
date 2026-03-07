import pandas as pd
import time
import requests
import os

API_URL = "http://127.0.0.1:8000/ingest"


# Use absolute path or correct relative path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(BASE_DIR, "..", "cleaner", "processed_.csv_file", "PUB_Demand_2020P.csv")

filename = os.path.basename(csv_path)
df = pd.read_csv(csv_path)

for idx, row in df.iterrows():
    data = row.to_dict()
    print(f"Sending row {idx} from {filename}")

    try:
        response = requests.post(API_URL, json=data)
        print("Server Response:", response.status_code)
    except requests.exceptions.RequestException as e:
        print("Error sending data:", e)

    time.sleep(1)   # increase if needed
