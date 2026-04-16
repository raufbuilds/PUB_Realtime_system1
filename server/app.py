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


@app.post("/ingest")
async def ingest(data: dict):
    conn = sqlite3.connect("data.db")
    curr = conn.cursor()
    curr.execute(
        "INSERT INTO demand (date, hour, demand) VALUES (?,?,?)",
        (data.get("Date"), data.get("Hour"), data.get("Ontario Demand")),
    )
    conn.commit()
    conn.close()
    return {"status": "saved"}


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
