from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import sqlite3
import json

app = FastAPI()

# ডাটাবেস সেটআপ
def init_db():
    conn = sqlite3.connect("data.db")
    curr = conn.cursor()
    curr.execute("CREATE TABLE IF NOT EXISTS demand (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, hour INTEGER, demand REAL)")
    conn.commit()
    conn.close()

init_db()

@app.post("/ingest")
async def ingest(data: dict):
    conn = sqlite3.connect("data.db")
    curr = conn.cursor()
    curr.execute("INSERT INTO demand (date, hour, demand) VALUES (?,?,?)", 
                 (data.get('Date'), data.get('Hour'), data.get('Ontario Demand')))
    conn.commit()
    conn.close()
    return {"status": "saved"}

@app.get("/stream")
async def stream():
    def event_generator():
        conn = sqlite3.connect("data.db")
        cursor = conn.cursor()
        last_id = 0
        
        while True:
            cursor.execute("SELECT id, date, hour, demand FROM demand WHERE id > ? ORDER BY id DESC LIMIT 1", (last_id,))
            row = cursor.fetchone()
            
            if row:
                last_id = row[0]
                record = {
                    "Date": row[1],
                    "Hour": row[2],
                    "Ontario Demand": row[3]
                }
                yield f"data: {json.dumps(record)}\n\n"
            
            import time
            time.sleep(1)
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")