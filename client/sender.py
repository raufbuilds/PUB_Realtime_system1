import pandas as pd
import time
import requests
import os
import glob

API_URL = "http://127.0.0.1:8000/ingest"
LOG_FILE = "sent_files.txt" # আমাদের লগবুক

def get_processed_files():
    if not os.path.exists(LOG_FILE): return set()
    with open(LOG_FILE, "r") as f:
        return set(line.strip() for line in f)

def mark_as_processed(filename):
    with open(LOG_FILE, "a") as f:
        f.write(filename + "\n")

processed_files = get_processed_files()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
folder_path = os.path.join(BASE_DIR, "..", "cleaner", "processed_.csv_file")
csv_files = glob.glob(os.path.join(folder_path, "*.csv"))

for file_path in csv_files:
    filename = os.path.basename(file_path)
    
    if filename in processed_files:
        print(f"Skipping {filename}, already sent.")
        continue # ফাইলটি আগে পাঠানো হয়ে থাকলে এড়িয়ে যাবে

    df = pd.read_csv(file_path)
    for idx, row in df.iterrows():
        try:
            requests.post(API_URL, json=row.to_dict())
            # ৭০০০ ডেটা থাকলে এখানে sleep কমাতে হবে (যেমন ০.১) যাতে দ্রুত যায়
            time.sleep(0.1) 
        except: continue
        
    mark_as_processed(filename) # পাঠানো শেষ হলে লগবুকে নাম লিখে রাখবে