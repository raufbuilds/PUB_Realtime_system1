import glob
import os
import time

import pandas as pd
import requests


API_URL = "http://127.0.0.1:8000/ingest"
LATEST_URL = "http://127.0.0.1:8000/latest"
LOG_FILE = "sent_files.txt"


def get_processed_files():
    if not os.path.exists(LOG_FILE):
        return set()
    with open(LOG_FILE, "r") as file_obj:
        return set(line.strip() for line in file_obj)


def mark_as_processed(filename):
    with open(LOG_FILE, "a") as file_obj:
        file_obj.write(filename + "\n")


def get_latest_progress():
    try:
        response = requests.get(LATEST_URL, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        print(f"Could not fetch latest server progress: {exc}")
        return None

    date_value = payload.get("Date")
    hour_value = payload.get("Hour")
    if date_value is None or hour_value is None:
        return None

    date_value = pd.to_datetime(date_value, errors="coerce")
    hour_value = pd.to_numeric(hour_value, errors="coerce")
    if pd.isna(date_value) or pd.isna(hour_value):
        return None

    return date_value.normalize(), int(hour_value)


def format_progress(progress):
    if progress is None:
        return "empty database"
    return f"{progress[0].date()} hour {progress[1]}"


def normalize_sender_dataframe(df):
    df = df.copy()
    df.columns = df.columns.str.strip()
    df = df.rename(
        columns={
            "Ontario_Demand": "Ontario Demand",
            "ontario demand": "Ontario Demand",
        }
    )
    df["Date"] = pd.to_datetime(df.get("Date"), errors="coerce")
    df["Hour"] = pd.to_numeric(df.get("Hour"), errors="coerce")
    df["Ontario Demand"] = pd.to_numeric(df.get("Ontario Demand"), errors="coerce")
    df = df.dropna(subset=["Date", "Hour", "Ontario Demand"])
    df["Hour"] = df["Hour"].astype(int)
    df = df[(df["Hour"] >= 0) & (df["Hour"] <= 23)]
    df["Date"] = df["Date"].dt.normalize()
    df = df.sort_values(["Date", "Hour"]).reset_index(drop=True)
    return df


def filter_rows_after_progress(df, latest_progress):
    if latest_progress is None or df.empty:
        return df

    latest_date, latest_hour = latest_progress
    mask = (df["Date"] > latest_date) | (
        (df["Date"] == latest_date) & (df["Hour"] > latest_hour)
    )
    return df[mask].reset_index(drop=True)


processed_files = get_processed_files()
latest_progress = get_latest_progress()
base_dir = os.path.dirname(os.path.abspath(__file__))
folder_path = os.path.join(base_dir, "..", "cleaner", "processed_.csv_file")

print(f"Looking for CSV files in: {folder_path}")
print(f"Folder exists: {os.path.exists(folder_path)}")

csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
csv_files.sort()
print(f"Found {len(csv_files)} CSV files")

if latest_progress is None:
    print("Server progress: empty database or progress unavailable")
    print("Starting from the beginning of the available CSV history")
else:
    print(f"Server progress: {format_progress(latest_progress)}")
    print(f"Starting after {format_progress(latest_progress)}")

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
            df = normalize_sender_dataframe(df)
            valid_count = len(df)
            if not df.empty:
                file_start = (df.iloc[0]["Date"], int(df.iloc[0]["Hour"]))
                file_end = (df.iloc[-1]["Date"], int(df.iloc[-1]["Hour"]))
                print(
                    f"File range: {format_progress(file_start)} -> "
                    f"{format_progress(file_end)}"
                )
            df = filter_rows_after_progress(df, latest_progress)
            print(f"Read {valid_count} valid rows from {filename}")

            if df.empty:
                print(
                    f"Skipping {filename}, all rows are at or before "
                    f"{format_progress(latest_progress)}"
                )
                mark_as_processed(filename)
                continue

            start_progress = (df.iloc[0]["Date"], int(df.iloc[0]["Hour"]))
            end_progress = (df.iloc[-1]["Date"], int(df.iloc[-1]["Hour"]))
            print(
                f"Sending {len(df)} new rows from {filename} "
                f"({format_progress(start_progress)} -> {format_progress(end_progress)})"
            )

            for idx, row in df.iterrows():
                try:
                    row_dict = row.to_dict()
                    row_dict["Date"] = row_dict["Date"].isoformat()  # Convert Timestamp to string
                    response = requests.post(API_URL, json=row_dict, timeout=10)
                    if response.status_code == 200:
                        result = response.json()
                        status = result.get("status")
                        if status == "saved":
                            print(f"Sent row {idx} successfully")
                            latest_progress = (row["Date"], int(row["Hour"]))
                        elif status == "skipped":
                            print(f"Skipped row {idx}, already exists")
                            latest_progress = (row["Date"], int(row["Hour"]))
                        else:
                            print(f"Processed row {idx} with status {status}")
                    else:
                        print(f"Row {idx} failed with status {response.status_code}")
                    time.sleep(1)
                except Exception as exc:
                    print(f"Error sending row {idx}: {exc}")

            mark_as_processed(filename)
            print(f"Marked {filename} as processed")
        except Exception as exc:
            print(f"Error reading {file_path}: {exc}")

print("\nAll done!")
