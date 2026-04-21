import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from print_monitor import PrintMonitor


monitor = PrintMonitor(poll_interval=1.0)
websocket_clients: set[WebSocket] = set()


def _on_state_update(state: list[dict]) -> None:
    if not websocket_clients:
        return
    payload = json.dumps({"event": "update", "data": state})
    dead: set[WebSocket] = set()
    for ws in list(websocket_clients):
        try:
            asyncio.run_coroutine_threadsafe(ws.send_text(payload), _loop)
        except Exception:
            dead.add(ws)
    websocket_clients.difference_update(dead)


_loop: asyncio.AbstractEventLoop


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop
    _loop = asyncio.get_event_loop()
    monitor.add_callback(_on_state_update)
    monitor.start()
    yield
    monitor.stop()


app = FastAPI(title="Print Tracker API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/printers", response_model=list[Any])
def list_printers():
    """Return current snapshot of all printers and their jobs."""
    return monitor.get_state()


@app.get("/printers/{printer_name}", response_model=dict)
def get_printer(printer_name: str):
    """Return a single printer by name."""
    for printer in monitor.get_state():
        if printer["name"] == printer_name:
            return printer
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Printer not found")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    websocket_clients.add(websocket)
    try:
        await websocket.send_text(
            json.dumps({"event": "init", "data": monitor.get_state()})
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        websocket_clients.discard(websocket)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
