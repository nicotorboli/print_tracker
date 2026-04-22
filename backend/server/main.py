import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import redis
import uvicorn
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ----- Redis -----

_redis = redis.from_url(
    os.getenv("UPSTASH_REDIS_URL", "redis://localhost:6379"),
    decode_responses=True,
)
HISTORY_KEY = "print:history"
EVENTS_KEY = "print:events"
MAX_HISTORY = 10_000
MAX_EVENTS = 1_000


def _save_history(entry: dict) -> None:
    score = time.time()
    _redis.zadd(HISTORY_KEY, {json.dumps(entry): score})
    _redis.zremrangebyrank(HISTORY_KEY, 0, -(MAX_HISTORY + 1))


def _save_event(entry: dict) -> None:
    _redis.zadd(EVENTS_KEY, {json.dumps(entry): time.time()})
    _redis.zremrangebyrank(EVENTS_KEY, 0, -(MAX_EVENTS + 1))


def _get_events(limit: int) -> list[dict]:
    raw = _redis.zrange(EVENTS_KEY, 0, -1, rev=True)
    return [json.loads(e) for e in raw[:limit]]


def _get_history(limit: int, user: str | None, printer: str | None) -> list[dict]:
    raw = _redis.zrange(HISTORY_KEY, 0, -1, rev=True)
    result = []
    for item in raw:
        entry = json.loads(item)
        if user and entry.get("user") != user:
            continue
        if printer and entry.get("printer_name") != printer:
            continue
        result.append(entry)
        if len(result) >= limit:
            break
    return result


# ----- modelos -----

class JobReport(BaseModel):
    job_id: int
    printer_name: str
    document: str
    pages_printed: int
    total_pages: int
    status: list[str]
    submitted: str | None = None


class AgentReport(BaseModel):
    hostname: str
    user: str
    jobs: list[JobReport]
    reported_at: str | None = None


class AgentEvent(BaseModel):
    hostname: str
    user: str
    type: str  # "started" | "stopped"
    timestamp: str


# ----- estado en memoria -----

_agents: dict[str, dict] = {}
_active_jobs: dict[str, dict[int, dict]] = {}
_ws_clients: set[WebSocket] = set()
_loop: asyncio.AbstractEventLoop


def _aggregated_by_printer() -> list[dict]:
    printers: dict[str, list[dict]] = {}
    for hostname, data in _agents.items():
        for job in data["jobs"]:
            printer = job["printer_name"]
            if printer not in printers:
                printers[printer] = []
            printers[printer].append({**job, "hostname": hostname, "user": data["user"]})
    return [{"printer_name": p, "jobs": jobs} for p, jobs in printers.items()]


def _process_report(report: AgentReport) -> None:
    hostname = report.hostname
    new_jobs = {j.job_id: j.model_dump() for j in report.jobs}
    prev_jobs = _active_jobs.get(hostname, {})

    # Trabajos que desaparecieron → guardar en historial
    for job_id, job_data in prev_jobs.items():
        if job_id not in new_jobs:
            _save_history({
                **job_data,
                "hostname": hostname,
                "user": report.user,
                "ended_at": (report.reported_at or datetime.now(timezone.utc).isoformat()),
            })

    _active_jobs[hostname] = new_jobs
    _agents[hostname] = {
        "user": report.user,
        "jobs": list(new_jobs.values()),
        "last_seen": time.time(),
    }


def _push_to_clients(payload: str) -> None:
    dead: set[WebSocket] = set()
    for ws in list(_ws_clients):
        try:
            asyncio.run_coroutine_threadsafe(ws.send_text(payload), _loop)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)


# ----- app -----

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop
    _loop = asyncio.get_event_loop()
    yield


app = FastAPI(title="Print Tracker Server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----- endpoints agente -----

@app.post("/agent/report", status_code=204)
def receive_report(report: AgentReport) -> None:
    _process_report(report)
    _push_to_clients(json.dumps({
        "event": "update",
        "data": _aggregated_by_printer(),
    }))


@app.post("/agent/event", status_code=204)
def receive_event(event: AgentEvent) -> None:
    entry = event.model_dump()
    _save_event(entry)
    _push_to_clients(json.dumps({"event": "agent_event", "data": entry}))


# ----- endpoints frontend -----

@app.get("/printers", response_model=list[Any])
def list_printers():
    return _aggregated_by_printer()


@app.get("/agents", response_model=list[Any])
def list_agents():
    now = time.time()
    return [
        {
            "hostname": hostname,
            "user": data["user"],
            "online": (now - data["last_seen"]) < 10,
            "jobs": data["jobs"],
        }
        for hostname, data in _agents.items()
    ]


@app.get("/events", response_model=list[Any])
def get_events(limit: int = Query(default=50, le=500)):
    return _get_events(limit=limit)


@app.get("/history", response_model=list[Any])
def get_history(
    user: str | None = Query(default=None),
    printer: str | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
):
    return _get_history(limit=limit, user=user, printer=printer)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        await websocket.send_text(json.dumps({
            "event": "init",
            "data": _aggregated_by_printer(),
        }))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(websocket)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
