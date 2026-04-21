# Print Tracker

Monitor en tiempo real de trabajos de impresión físicos en Windows.
Muestra cuántas páginas se imprimieron realmente (ej: "33 / 100") en lugar de solo "enviado a la impresora".

## Arquitectura

```
backend/   Python + FastAPI  →  lee la cola de Windows via win32print
frontend/  (próximamente)    →  consume la API REST y WebSocket
```

### Escenario de oficina

Cada usuario tiene su propia PC. Cuando quieren imprimir, mandan el trabajo a la PC-A (la que tiene las impresoras conectadas). El backend corre en PC-A y ve los trabajos de **todos los usuarios** porque Windows guarda el usuario de red de origen en el spooler.

```
PC usuario 1 (maria)  ──┐
PC usuario 2 (carlos) ──┤──▶  PC-A (print server)  ──▶  Impresora 1
PC usuario 3 (juan)   ──┘     backend Python         ──▶  Impresora 2
                                    │
                             http://IP-PC-A:8000
                                    │
                         Cualquier navegador de la oficina
```

## Requisitos

- Windows 10/11
- Python 3.11+
- Las impresoras instaladas en la PC donde corre el backend

## Levantar el backend

```bash
cd backend
pip install -r requirements.txt
python main.py
```

El servidor arranca en `http://localhost:8000`.  
Desde otras PCs de la oficina: `http://IP-DE-LA-PC:8000`.

## API

| Método | Ruta                       | Descripción                                      |
|--------|----------------------------|--------------------------------------------------|
| GET    | `/printers`                | Lista todas las impresoras y sus trabajos activos |
| GET    | `/printers/{printer_name}` | Detalle de una impresora específica              |
| WS     | `/ws`                      | WebSocket: push de actualizaciones cada ~1 seg   |

### Ejemplo de respuesta (`/printers`)

```json
[
  {
    "name": "HP-Oficina",
    "status": ["printing"],
    "jobs": [
      {
        "job_id": 42,
        "user": "maria",
        "document": "Informe.pdf",
        "pages_printed": 33,
        "total_pages": 100,
        "status": ["printing"],
        "submitted": "2026-04-21T10:30:00"
      },
      {
        "job_id": 43,
        "user": "carlos",
        "document": "Factura.xlsx",
        "pages_printed": 2,
        "total_pages": 5,
        "status": ["spooling"],
        "submitted": "2026-04-21T10:31:00"
      }
    ]
  },
  {
    "name": "Canon-Color",
    "status": ["ready"],
    "jobs": []
  }
]
```

### WebSocket (`ws://localhost:8000/ws`)

Al conectar recibe `{"event": "init", "data": [...]}` con el estado actual.  
Cada segundo recibe `{"event": "update", "data": [...]}` con el estado actualizado.

## Cómo funciona el backend

El flujo tiene tres capas:

### 1. Windows Spooler (la fuente de datos)

Cuando un usuario manda a imprimir desde su PC, el spooler de Windows en PC-A recibe el trabajo y registra:

- Quién lo mandó (`user`)
- Qué archivo es (`document`)
- Cuántas páginas tiene en total (`total_pages`)
- Cuántas páginas se imprimieron físicamente hasta ahora (`pages_printed`) — este valor se actualiza en tiempo real mientras la impresora trabaja

### 2. `print_monitor.py` (el lector)

Un hilo de fondo se ejecuta cada 1 segundo y hace lo siguiente:

**Paso 1** — pregunta a Windows qué impresoras existen y su estado:
```
HP-Oficina   →  status: 0x00000400  →  ["printing"]
Canon-Color  →  status: 0x00000000  →  ["ready"]
```

**Paso 2** — el estado de Windows es un número binario donde cada bit significa algo distinto. Lo decodificamos a texto legible. Por ejemplo `0x00000028` significa `["paper_out", "manual_feed"]` al mismo tiempo.

**Paso 3** — para cada impresora, abre la cola y lee todos los trabajos activos:
```python
win32print.EnumJobs(handle, 0, 9999, level=2)
# level=2 es el único que incluye PagesPrinted
```

**Paso 4** — con el estado completo, notifica a todos los clientes WebSocket conectados.

### 3. `main.py` (el servidor HTTP)

Expone los datos de dos formas:

- **REST** (`GET /printers`): devuelve el último snapshot guardado en memoria, sin ir a Windows cada vez.
- **WebSocket** (`WS /ws`): cuando un navegador se conecta recibe el estado actual, y después recibe un push automático cada vez que algo cambia.

El hilo de polling es síncrono y el servidor es asíncrono (asyncio). El puente entre ambos mundos es `asyncio.run_coroutine_threadsafe`, que permite al hilo enviar mensajes a los WebSockets sin bloquear el servidor.

### Timeline de ejemplo

```
t=0s    python main.py arranca, hilo de polling se inicia

t=5s    maria manda a imprimir Informe.pdf (100 páginas) desde su PC
        Windows spooler lo registra en PC-A

t=6s    hilo lee → HP-Oficina: job 42, maria, 0/100, spooling
        → navegadores reciben el update

t=7s    la impresora empieza a imprimir físicamente
        hilo lee → job 42, maria, 1/100, printing

t=40s   hilo lee → job 42, maria, 33/100, printing
        → navegadores muestran "33 / 100"

t=41s   papel atascado
        hilo lee → HP-Oficina status: ["paper_jam"]
                   job 42, maria, 33/100, paused
        → navegadores reflejan el atasco en tiempo real

t=42s   alguien destasca el papel, sigue imprimiendo
        hilo lee → job 42, maria, 34/100, printing

t=106s  trabajo terminado
        job 42 desaparece de la cola (Windows lo elimina automáticamente)
```
