from contextlib import contextmanager
import asyncio
import json
import os
from queue import Queue
import sqlite3
from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse


app = FastAPI()


class RequestSizeLimitMiddleware:
    def __init__(self, app, max_size: int):
        self.app = app
        self.max_size = max_size

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = 0
        for header_name, header_value in scope.get("headers", []):
            if header_name == b"content-length":
                try:
                    content_length = int(header_value.decode("latin1"))
                except ValueError:
                    content_length = 0
                break

        if content_length > self.max_size:
            response = JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )
            await response(scope, receive, send)
            return

        if scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        body = b""
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.request":
                body += message.get("body", b"")
                more_body = message.get("more_body", False)
                if len(body) > self.max_size:
                    response = JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large"},
                    )
                    await response(scope, receive, send)
                    return
            else:
                await self.app(scope, receive, send)
                return

        body_sent = False

        async def replay_receive():
            nonlocal body_sent
            if body_sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            body_sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay_receive, send)


def load_env_file(path=".env"):
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()

DB_PATH = os.getenv("DB_PATH", "data.db")
DB_POOL_SIZE = max(1, int(os.getenv("DB_POOL_SIZE", "5")))
MAX_REQUEST_SIZE_BYTES = int(os.getenv("MAX_REQUEST_SIZE_BYTES", str(1024 * 1024)))

connection_pool = Queue(maxsize=DB_POOL_SIZE)
app.add_middleware(RequestSizeLimitMiddleware, max_size=MAX_REQUEST_SIZE_BYTES)


def create_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


for _ in range(DB_POOL_SIZE):
    connection_pool.put(create_connection())


@contextmanager
def get_connection():
    conn = connection_pool.get()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        connection_pool.put(conn)


def init_db():
    with get_connection() as conn:
        curr = conn.cursor()
        curr.execute(
            "CREATE TABLE IF NOT EXISTS demand ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "date TEXT, hour INTEGER, demand REAL)"
        )
        curr.execute(
            "CREATE INDEX IF NOT EXISTS idx_demand_date_hour "
            "ON demand(date, hour)"
        )
        conn.commit()


init_db()


def fetch_rows(after_id: int = 0, limit: Optional[int] = None):
    with get_connection() as conn:
        cursor = conn.cursor()

        query = "SELECT id, date, hour, demand FROM demand WHERE id > ? ORDER BY id ASC"
        params = [after_id]

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        return cursor.fetchall()


def fetch_latest_progress():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, date, hour, demand FROM demand "
            "ORDER BY date DESC, hour DESC, id DESC LIMIT 1"
        )
        return cursor.fetchone()


@app.post("/ingest")
async def ingest(data: dict):
    date_value = data.get("Date")
    hour_value = data.get("Hour")
    demand_value = data.get("Ontario Demand")

    with get_connection() as conn:
        curr = conn.cursor()
        curr.execute(
            "SELECT id FROM demand WHERE date = ? AND hour = ? LIMIT 1",
            (date_value, hour_value),
        )
        existing = curr.fetchone()

        if existing:
            return {"status": "skipped", "reason": "duplicate", "id": existing[0]}

        curr.execute(
            "INSERT INTO demand (date, hour, demand) VALUES (?,?,?)",
            (date_value, hour_value, demand_value),
        )
        conn.commit()
        inserted_id = curr.lastrowid
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
async def stream(request: Request):
    async def event_generator():
        last_id = 0

        while True:
            if await request.is_disconnected():
                break

            try:
                rows = fetch_rows(after_id=last_id)
                for row in rows:
                    if await request.is_disconnected():
                        return

                    last_id = row[0]
                    record = {
                        "id": row[0],
                        "Date": row[1],
                        "Hour": row[2],
                        "Ontario Demand": row[3],
                    }
                    yield f"data: {json.dumps(record)}\n\n"
            except Exception as exc:
                error_payload = {"error": "stream_fetch_failed", "detail": str(exc)}
                yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
