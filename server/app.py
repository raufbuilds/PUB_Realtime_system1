from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
import asyncio
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

latest_data = []


@app.post("/ingest")
async def ingest(data: dict):
    latest_data.append(data)
    return JSONResponse({"message": "Data received"})


@app.get("/stream")
async def stream():

    async def event_generator():
        last_index = 0
        while True:
            if last_index < len(latest_data):
                payload = json.dumps(latest_data[last_index])
                yield {"data": payload}
                last_index += 1

            await asyncio.sleep(0.5)  # keepalive rate

    return EventSourceResponse(event_generator())

