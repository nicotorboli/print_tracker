import win32print  # type: ignore[import-untyped]
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from config import PRINT_SERVER, PRINTERS


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

PRINTER_STATUS_MAP = {
    0x00000000: "ready",
    0x00000001: "paused",
    0x00000002: "error",
    0x00000004: "pending_deletion",
    0x00000008: "paper_jam",
    0x00000010: "paper_out",
    0x00000020: "manual_feed",
    0x00000040: "paper_problem",
    0x00000080: "offline",
    0x00000100: "io_active",
    0x00000200: "busy",
    0x00000400: "printing",
    0x00000800: "output_bin_full",
    0x00001000: "not_available",
    0x00002000: "waiting",
    0x00004000: "processing",
    0x00008000: "initializing",
    0x00010000: "warming_up",
    0x00020000: "toner_low",
    0x00040000: "no_toner",
    0x00080000: "page_punt",
    0x00100000: "user_intervention",
    0x00200000: "out_of_memory",
    0x00400000: "door_open",
    0x00800000: "server_unknown",
    0x01000000: "power_save",
}


def _decode_status(status_code: int, status_map: dict) -> list[str]:
    return [label for bit, label in status_map.items() if status_code & bit]


@dataclass
class PrintJob:
    job_id: int
    printer_name: str
    document: str
    user: str
    pages_printed: int
    total_pages: int
    status_code: int
    status: list[str]
    submitted: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PrinterState:
    name: str
    status_code: int
    status: list[str]
    jobs: list[PrintJob] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status_code": self.status_code,
            "status": self.status,
            "jobs": [j.to_dict() for j in self.jobs],
        }


def _format_systime(st) -> Optional[str]:
    if st is None:
        return None
    try:
        return f"{st[0]:04d}-{st[1]:02d}-{st[3]:02d}T{st[4]:02d}:{st[5]:02d}:{st[6]:02d}"
    except Exception:
        return None


def _read_jobs(printer_name: str) -> list[PrintJob]:
    jobs: list[PrintJob] = []
    try:
        handle = win32print.OpenPrinter(printer_name)
        try:
            raw_jobs = win32print.EnumJobs(handle, 0, 9999, 2)
            for j in raw_jobs:
                jobs.append(PrintJob(
                    job_id=j["JobId"],
                    printer_name=printer_name,
                    document=j.get("pDocument", ""),
                    user=j.get("pUserName", ""),
                    pages_printed=j.get("PagesPrinted", 0),
                    total_pages=j.get("TotalPages", 0),
                    status_code=j.get("Status", 0),
                    status=_decode_status(j.get("Status", 0), JOB_STATUS_MAP),
                    submitted=_format_systime(j.get("Submitted")),
                ))
        finally:
            win32print.ClosePrinter(handle)
    except Exception:
        pass
    return jobs


def _unc(printer_name: str) -> str:
    """Devuelve el UNC completo si hay un servidor configurado y el nombre no es ya UNC."""
    if PRINT_SERVER and not printer_name.startswith("\\\\"):
        return f"\\\\{PRINT_SERVER}\\{printer_name}"
    return printer_name


def _enumerate_printer_names() -> list[tuple[str, int]]:
    """Retorna lista de (nombre_unc, status_code)."""
    if PRINTERS:
        # Lista explícita: abrimos cada una para leer su estado actual
        result = []
        for name in PRINTERS:
            full_name = _unc(name)
            try:
                handle = win32print.OpenPrinter(full_name)
                info = win32print.GetPrinter(handle, 2)
                win32print.ClosePrinter(handle)
                result.append((full_name, info.get("Status", 0)))
            except Exception:
                result.append((full_name, 0))
        return result

    # Sin lista explícita: enumerar todas las del servidor (o locales)
    server = PRINT_SERVER or None
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    if server:
        flags = win32print.PRINTER_ENUM_SHARED
    try:
        raw = win32print.EnumPrinters(flags, server, 2)
        return [(p["pPrinterName"], p.get("Status", 0)) for p in raw]
    except Exception:
        return []


def get_printers() -> list[PrinterState]:
    states: list[PrinterState] = []
    for name, status_code in _enumerate_printer_names():
        states.append(PrinterState(
            name=name,
            status_code=status_code,
            status=_decode_status(status_code, PRINTER_STATUS_MAP),
            jobs=_read_jobs(name),
        ))
    return states


class PrintMonitor:
    def __init__(self, poll_interval: float = 1.0):
        self.poll_interval = poll_interval
        self._state: list[PrinterState] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: list = []

    def add_callback(self, fn) -> None:
        self._callbacks.append(fn)

    def remove_callback(self, fn) -> None:
        if fn in self._callbacks:
            self._callbacks.remove(fn)

    def get_state(self) -> list[dict]:
        with self._lock:
            return [p.to_dict() for p in self._state]

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _poll_loop(self) -> None:
        while self._running:
            new_state = get_printers()
            with self._lock:
                self._state = new_state
            snapshot = [p.to_dict() for p in new_state]
            for cb in list(self._callbacks):
                try:
                    cb(snapshot)
                except Exception:
                    pass
            time.sleep(self.poll_interval)
