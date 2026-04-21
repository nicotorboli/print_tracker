import os


def _parse_list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


# Nombre NetBIOS o IP del servidor de impresión. Ej: "SERVIDOR" o "192.168.1.10"
# Si está vacío, se asume que el script corre en el servidor local.
PRINT_SERVER: str = os.getenv("PRINT_SERVER", "")

# Lista explícita de impresoras a monitorear. Puede ser nombre local o UNC.
# Ej: "HP-Oficina,Canon-Color"  o  "\\SERVIDOR\HP-Oficina,\\SERVIDOR\Canon-Color"
# Si está vacío, se enumeran todas las impresoras disponibles en el servidor.
PRINTERS: list[str] = _parse_list(os.getenv("PRINTERS", ""))

# Segundos entre cada lectura de la cola
POLL_INTERVAL: float = float(os.getenv("POLL_INTERVAL", "1.0"))
