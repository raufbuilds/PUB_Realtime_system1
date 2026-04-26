from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
import sqlite3
import json
from typing import Optional


app = FastAPI()


def init_db():
    conn = sqlite3.connect("data.db")
    curr = conn.cursor()
    curr.execute(
        "CREATE TABLE IF NOT EXISTS demand ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "date TEXT, hour INTEGER, demand REAL)"
    )
    conn.commit()
    conn.close()


init_db()


def fetch_rows(after_id: int = 0, limit: Optional[int] = None):
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()

    query = "SELECT id, date, hour, demand FROM demand WHERE id > ? ORDER BY id ASC"
    params = [after_id]

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return rows


def fetch_latest_progress():
    conn = sqlite3.connect("data.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, date, hour, demand FROM demand "
        "ORDER BY date DESC, hour DESC, id DESC LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()
    return row


@app.post("/ingest")
async def ingest(data: dict):
    date_value = data.get("Date")
    hour_value = data.get("Hour")
    demand_value = data.get("Ontario Demand")

    conn = sqlite3.connect("data.db")
    curr = conn.cursor()
    curr.execute(
        "SELECT id FROM demand WHERE date = ? AND hour = ? LIMIT 1",
        (date_value, hour_value),
    )
    existing = curr.fetchone()

    if existing:
        conn.close()
        return {"status": "skipped", "reason": "duplicate", "id": existing[0]}

    curr.execute(
        "INSERT INTO demand (date, hour, demand) VALUES (?,?,?)",
        (date_value, hour_value, demand_value),
    )
    conn.commit()
    inserted_id = curr.lastrowid
    conn.close()
    return {"status": "saved", "id": inserted_id}


@app.get("/records")
async def records(
    after_id: int = Query(0, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=10000),
):
    rows = fetch_rows(after_id=after_id, limit=limit)
    return [
        {
            "id": row[0],
            "Date": row[1],
            "Hour": row[2],
            "Ontario Demand": row[3],
        }
        for row in rows
    ]


@app.get("/latest")
async def latest():
    row = fetch_latest_progress()
    if row is None:
        return {"id": None, "Date": None, "Hour": None, "Ontario Demand": None}

    return {
        "id": row[0],
        "Date": row[1],
        "Hour": row[2],
        "Ontario Demand": row[3],
    }


@app.get("/stream")
async def stream():
    def event_generator():
        last_id = 0

        while True:
            rows = fetch_rows(after_id=last_id)
            for row in rows:
                last_id = row[0]
                record = {
                    "id": row[0],
                    "Date": row[1],
                    "Hour": row[2],
                    "Ontario Demand": row[3],
                }
                yield f"data: {json.dumps(record)}\n\n"

            import time

            time.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
