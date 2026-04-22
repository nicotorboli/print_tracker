# Print Tracker

Monitor en tiempo real de trabajos de impresión físicos en Windows.
Muestra quién está imprimiendo, cuántas páginas pidió y cuántas van saliendo — ej: "maria → Informe.pdf → 33 / 100". Guarda historial completo de todos los trabajos y eventos del sistema.

## Arquitectura

No hay PC central dedicada. Cada usuario tiene su notebook. El servidor corre en Render (nube) y la base de datos en Upstash (Redis).

```
Notebook maria  (agent) ──POST──▶
Notebook carlos (agent) ──POST──▶  Render (servidor)  ──▶  Upstash (Redis)
Notebook juan   (agent) ──POST──▶                      ──▶  Frontend
```

Si se corta internet en la oficina, el agente guarda todo en `pending.json` y lo manda al servidor cuando vuelve la conexión — sin perder datos.

```
backend/
  agent/
    agent.py          →  corre en cada notebook (Windows)
    requirements.txt
  server/
    main.py           →  corre en Render
    requirements.txt
instalar.bat          →  instala el agente como servicio de Windows
desinstalar.bat       →  desinstala el agente (requiere clave)
detener.bat           →  detiene el agente (requiere clave)
iniciar.bat           →  inicia el agente (requiere clave)
```

---

## Antes de ir a la oficina (desde tu PC)

### 1. Compilar el agente en un .exe

```bash
pip install pyinstaller
cd backend/agent
pyinstaller --onefile agent.py
# genera: backend/agent/dist/agent.exe
```

### 2. Descargar nssm.exe

Entrar a `https://nssm.cc/download`, descargar el ZIP y extraer `win64\nssm.exe`.

### 3. Cambiar la clave en los .bat

Abrir [desinstalar.bat](desinstalar.bat), [detener.bat](detener.bat) e [iniciar.bat](iniciar.bat) y reemplazar `admin1234` por la clave real en los tres archivos.

### 4. Editar instalar.bat con la URL del servidor

Abrir [instalar.bat](instalar.bat) y cambiar:
```bat
set SERVER_URL=http://TU_IP_SERVIDOR:8000
```
Por la URL de Render:
```bat
set SERVER_URL=https://print-tracker.onrender.com
```

### 5. Subir a GitHub Releases

1. Entrar a `github.com/tu-usuario/print-tracker` → **Releases** → **Create a new release**
2. Tag: `v1.0.0`
3. Subir los 6 archivos como assets:
   - `backend/agent/dist/agent.exe`
   - `nssm.exe`
   - `instalar.bat`
   - `desinstalar.bat`
   - `detener.bat`
   - `iniciar.bat`
4. **Publish release**

---

## Deploy del servidor en Render

### 1. Crear la base de datos en Upstash

1. Entrar a `upstash.com` y crear una cuenta
2. Crear una base de datos Redis → elegir la región más cercana
3. Copiar la **Redis URL** (formato: `rediss://default:password@host:port`)

### 2. Deploy en Render

1. Entrar a `render.com` y crear una cuenta
2. **New** → **Web Service** → conectar el repo de GitHub
3. Configurar:
   - **Root directory:** `backend/server`
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `python main.py`
4. En **Environment Variables** agregar:
   - `UPSTASH_REDIS_URL` → pegar la Redis URL de Upstash
5. **Deploy**

Verificar que funciona abriendo `https://tu-app.onrender.com/printers` en el navegador.

---

## Instalación del agente en cada notebook

### Opción A — GitHub Releases (recomendada)

1. Abrir el navegador y entrar a `github.com/tu-usuario/print-tracker/releases`
2. Descargar los 6 archivos en la misma carpeta
3. Clic derecho en `instalar.bat` → **Ejecutar como administrador**

El agente queda instalado como servicio de Windows, arranca automáticamente con la notebook y solo puede detenerse o desinstalarse con clave.

### Opción B — ZIP del repo

1. Entrar a `github.com/tu-usuario/print-tracker` → **Code** → **Download ZIP**
2. Extraer el ZIP
3. Clic derecho en `instalar.bat` → **Ejecutar como administrador**

### Opción C — PowerShell

```powershell
powershell -ExecutionPolicy Bypass -Command "Invoke-WebRequest https://github.com/tu-usuario/print-tracker/releases/latest/download/instalar.bat -OutFile instalar.bat; .\instalar.bat"
```

### Verificar que funciona

Abrir en el navegador:
```
https://tu-app.onrender.com/agents
```
La notebook instalada tiene que aparecer con `"online": true`.

---

## Gestión del agente (requiere clave)

| Script | Qué hace |
|---|---|
| `instalar.bat` | Instala el agente como servicio (sin clave) |
| `detener.bat` | Detiene el agente sin desinstalarlo |
| `iniciar.bat` | Vuelve a iniciar el agente |
| `desinstalar.bat` | Detiene, elimina el servicio y borra los archivos |

Todos los scripts excepto `instalar.bat` requieren clave de administrador. Los usuarios estándar no pueden detener el servicio directamente desde Windows porque los permisos del servicio están restringidos por `sc sdset` durante la instalación.

Cuando el agente se detiene o se inicia, el servidor lo registra automáticamente y el frontend puede mostrarlo.

---

## Qué pasa si se corta internet

El agente detecta que el servidor no responde y guarda cada cambio en `pending.json` en `C:\PrintTracker\`. Cuando vuelve internet, manda todo en orden antes de seguir reportando normal.

```
Internet se corta:
  → agente guarda en pending.json
  → sigue guardando cada cambio

Internet vuelve:
  → agente manda todo pending.json al servidor en orden
  → servidor guarda el historial completo en Redis
  → frontend muestra todo lo que pasó mientras no había internet
```

---

## Agregar features y deployar

**1. Desarrollar y pushear desde tu PC:**
```bash
git add .
git commit -m "nueva feature"
git push
```

**2. Servidor en Render:** se redeploya automáticamente con cada push a `main`.

**3. Agentes en las notebooks** (solo si cambió `agent.py`):
- Compilar nuevo `agent.exe` con PyInstaller
- Subir nueva versión a GitHub Releases
- En cada notebook: descargar el nuevo `agent.exe`, reemplazar en `C:\PrintTracker\` y ejecutar:
```bash
nssm restart PrintTrackerAgent
```

---

## Soporte remoto

**AnyDesk** — instalar en las notebooks de la oficina y en la tuya. Cuando algo falla, conectarse con el ID de esa notebook.

**Tailscale** — crea una VPN privada entre todas las notebooks sin tocar el router. Permite reiniciar servicios y ver logs desde cualquier red.

**Comandos útiles de NSSM:**
```bash
nssm status PrintTrackerAgent     # ver estado
nssm restart PrintTrackerAgent    # reiniciar (requiere admin de Windows)
```

---

## API

| Método | Ruta            | Descripción                                            |
|--------|-----------------|--------------------------------------------------------|
| POST   | `/agent/report` | Usado por los agentes para reportar su cola local      |
| POST   | `/agent/event`  | Usado por los agentes para reportar inicio/detención   |
| GET    | `/printers`     | Todos los trabajos activos agrupados por impresora     |
| GET    | `/agents`       | Vista por notebook: quién está online y qué imprime    |
| GET    | `/history`      | Historial de trabajos terminados                       |
| GET    | `/events`       | Historial de eventos (agente iniciado/detenido)        |
| WS     | `/ws`           | WebSocket: push en tiempo real                         |

### Filtros de `/history`

```
GET /history?user=maria
GET /history?printer=HP-Oficina
GET /history?user=maria&printer=HP-Oficina&limit=50
```

### Ejemplo — `GET /printers`

```json
[
  {
    "printer_name": "HP-Oficina",
    "jobs": [
      {
        "job_id": 42,
        "hostname": "MARIA-PC",
        "user": "maria",
        "document": "Informe.pdf",
        "pages_printed": 33,
        "total_pages": 100,
        "status": ["printing"],
        "submitted": "2026-04-21T10:30:00"
      }
    ]
  }
]
```

### Ejemplo — `GET /history`

```json
[
  {
    "job_id": 41,
    "hostname": "CARLOS-PC",
    "user": "carlos",
    "printer_name": "HP-Oficina",
    "document": "Factura.xlsx",
    "pages_printed": 5,
    "total_pages": 5,
    "status": ["complete"],
    "submitted": "2026-04-21T09:15:00",
    "ended_at": "2026-04-21T09:16:30"
  }
]
```

### Ejemplo — `GET /events`

```json
[
  {
    "hostname": "MARIA-PC",
    "user": "maria",
    "type": "stopped",
    "timestamp": "2026-04-21T10:35:00"
  },
  {
    "hostname": "MARIA-PC",
    "user": "maria",
    "type": "started",
    "timestamp": "2026-04-21T08:00:00"
  }
]
```

### WebSocket (`wss://tu-app.onrender.com/ws`)

| Evento | Cuándo se dispara |
|---|---|
| `init` | Al conectar — estado actual completo |
| `update` | Cada vez que un agente reporta cambios |
| `agent_event` | Cuando un agente se inicia o detiene |

---

## Cómo funciona

### Agente (`agent.py`)

Corre en cada notebook. Al arrancar manda evento `started`. Al cerrarse manda evento `stopped`. Cada segundo compara el estado actual de la cola con el último estado enviado. Si cambió algo:

1. Intenta mandar primero todo lo que esté en `pending.json`
2. Si el servidor responde, manda el estado actual
3. Si el servidor no responde, agrega el estado actual a `pending.json`

Solo guarda cuando algo cambia — no genera entradas idénticas.

### Servidor (`server/main.py`)

Recibe los reportes y:
- Detecta trabajos que desaparecieron de la cola → los guarda en Redis como historial
- Actualiza el estado en memoria para tiempo real
- Recibe eventos de inicio/detención → los guarda en Redis
- Empuja todos los cambios a los clientes WebSocket conectados

### Redis (Upstash)

Dos sorted sets ordenados por timestamp:

| Key | Contenido | Máximo |
|---|---|---|
| `print:history` | Trabajos terminados | 10.000 entradas |
| `print:events` | Eventos inicio/detención | 1.000 entradas |

Las entradas más viejas se eliminan automáticamente cuando se alcanza el límite.

Un agente se considera **offline** si no reportó en los últimos 10 segundos.
