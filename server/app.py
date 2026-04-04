from fastapi import FastAPI
import sqlite3

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