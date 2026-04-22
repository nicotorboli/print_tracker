import os
import time
import json
import hashlib
import signal
import socket
import getpass
import sys
from datetime import datetime, timezone

import requests
import win32print  # type: ignore[import-untyped]

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1.0"))
PENDING_FILE = os.path.join(os.path.dirname(__file__), "pending.json")

HOSTNAME = socket.gethostname()
CURRENT_USER = getpass.getuser()

JOB_STATUS_MAP = {
    0x00000001: "paused",
    0x00000002: "error",
    0x00000004: "deleting",
    0x00000008: "spooling",
    0x00000010: "printing",
    0x00000020: "offline",
    0x00000040: "paper_out",
    0x00000080: "printed",
    0x00000100: "deleted",
    0x00000200: "blocked",
    0x00000400: "user_intervention",
    0x00000800: "restarting",
    0x00001000: "complete",
}


def _decode_status(code: int) -> list[str]:
    return [label for bit, label in JOB_STATUS_MAP.items() if code & bit]


def _format_systime(st) -> str | None:
    if st is None:
        return None
    try:
        return f"{st[0]:04d}-{st[1]:02d}-{st[3]:02d}T{st[4]:02d}:{st[5]:02d}:{st[6]:02d}"
    except Exception:
        return None


def read_local_jobs() -> list[dict]:
    jobs = []
    try:
        printers = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS,
            None, 2,
        )
        for p in printers:
            printer_name = p["pPrinterName"]
            try:
                handle = win32print.OpenPrinter(printer_name)
                try:
                    for j in win32print.EnumJobs(handle, 0, 9999, 2):
                        jobs.append({
                            "job_id": j["JobId"],
                            "printer_name": printer_name,
                            "document": j.get("pDocument", ""),
                            "pages_printed": j.get("PagesPrinted", 0),
                            "total_pages": j.get("TotalPages", 0),
                            "status": _decode_status(j.get("Status", 0)),
                            "submitted": _format_systime(j.get("Submitted")),
                        })
                finally:
                    win32print.ClosePrinter(handle)
            except Exception:
                pass
    except Exception:
        pass
    return jobs


# ----- cola local (pending.json) -----

def _load_pending() -> list[dict]:
    if not os.path.exists(PENDING_FILE):
        return []
    try:
        with open(PENDING_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _save_pending(pending: list[dict]) -> None:
    try:
        with open(PENDING_FILE, "w") as f:
            json.dump(pending, f)
    except Exception:
        pass


def _jobs_fingerprint(jobs: list[dict]) -> str:
    return hashlib.md5(json.dumps(jobs, sort_keys=True).encode()).hexdigest()


def _build_payload(jobs: list[dict]) -> dict:
    return {
        "hostname": HOSTNAME,
        "user": CURRENT_USER,
        "jobs": jobs,
        "reported_at": datetime.now(timezone.utc).isoformat(),
    }


def _post(payload: dict) -> bool:
    try:
        r = requests.post(f"{SERVER_URL}/agent/report", json=payload, timeout=3)
        return r.status_code == 204
    except Exception:
        return False


def _post_event(event_type: str) -> None:
    try:
        requests.post(
            f"{SERVER_URL}/agent/event",
            json={
                "hostname": HOSTNAME,
                "user": CURRENT_USER,
                "type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            timeout=3,
        )
    except Exception:
        pass


def _on_shutdown(signum, frame) -> None:
    _post_event("stopped")
    sys.exit(0)


def _drain_pending() -> bool:
    """Intenta mandar todo lo pendiente. Retorna True si quedó vacío."""
    pending = _load_pending()
    if not pending:
        return True
    sent = 0
    for payload in pending:
        if _post(payload):
            sent += 1
        else:
            break
    remaining = pending[sent:]
    if remaining:
        _save_pending(remaining)
        return False
    else:
        if os.path.exists(PENDING_FILE):
            os.remove(PENDING_FILE)
        return True


# ----- loop principal -----

def main() -> None:
    signal.signal(signal.SIGTERM, _on_shutdown)
    signal.signal(signal.SIGINT, _on_shutdown)

    print(f"Agente iniciado — PC: {HOSTNAME}, usuario: {CURRENT_USER}")
    print(f"Servidor: {SERVER_URL}")
    _post_event("started")

    last_fingerprint = ""

    while True:
        jobs = read_local_jobs()
        fingerprint = _jobs_fingerprint(jobs)
        changed = fingerprint != last_fingerprint

        if changed:
            payload = _build_payload(jobs)
            pending_clear = _drain_pending()

            if pending_clear and _post(payload):
                last_fingerprint = fingerprint
            else:
                pending = _load_pending()
                pending.append(payload)
                _save_pending(pending)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
