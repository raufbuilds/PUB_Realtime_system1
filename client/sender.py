import pandas as pd
import time
import requests
import os
import glob

API_URL = "http://127.0.0.1:8000/ingest"
LOG_FILE = "sent_files.txt"

def get_processed_files():
    if not os.path.exists(LOG_FILE): 
        return set()
    with open(LOG_FILE, "r") as f:
        return set(line.strip() for line in f)

def mark_as_processed(filename):
    with open(LOG_FILE, "a") as f:
        f.write(filename + "\n")

processed_files = get_processed_files()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
folder_path = os.path.join(BASE_DIR, "..", "cleaner", "processed_.csv_file")

print(f"Looking for CSV files in: {folder_path}")
print(f"Folder exists: {os.path.exists(folder_path)}")

csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
print(f"Found {len(csv_files)} CSV files")

if not csv_files:
    print("ERROR: No CSV files found!")
else:
    for file_path in csv_files:
        filename = os.path.basename(file_path)
        print(f"\nProcessing: {filename}")
        
        if filename in processed_files:
            print(f"Skipping {filename}, already sent.")
            continue

        try:
            df = pd.read_csv(file_path)
            print(f"Read {len(df)} rows from {filename}")
            
            for idx, row in df.iterrows():
                try:
                    response = requests.post(API_URL, json=row.to_dict())
                    if response.status_code == 200:
                        print(f"✓ Row {idx} sent successfully")
                    else:
                        print(f"✗ Row {idx} failed with status {response.status_code}")
                    time.sleep(1)
                except Exception as e:
                    print(f"Error sending row {idx}: {e}")
            
            mark_as_processed(filename)
            print(f"✓ Marked {filename} as processed")
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

print("\nAll done!")