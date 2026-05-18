# Local Dev — Arranque del stack

Guía operativa para correr el sistema (backend FastAPI + frontend React) en una PC de desarrollo.

## Quick start (ya tenés el setup hecho)

```bash
# Terminal 1 — backend
cd <project-root>
./run-backend.sh        # arranca uvicorn en localhost:8000 con --env-file .env

# Terminal 2 — frontend
cd <project-root>/frontend
npm run dev             # arranca Vite en localhost:5173

# Browser
# http://localhost:5173 → login Google → entrás como admin (según RBAC_ROLE_MAPPING)
```

Frenar: `Ctrl+C` en cada terminal.

---

## Setup from scratch (primera vez)

### Requisitos

- Python 3.12+ (3.14 funciona con un workaround, ver troubleshooting)
- Node 20+ con npm
- Git Bash en Windows (los comandos de abajo asumen Unix shell syntax)

### 1. Backend Python — venv y dependencias

```bash
cd <project-root>
python -m venv venv
source venv/Scripts/activate          # en Windows; en Linux/Mac: source venv/bin/activate
python -m pip install --upgrade pip
```

**Importante:** `pip install -r backend/requirements.txt` directo **falla** por conflicto declarativo entre `supabase 2.7.x` (pide `httpx<0.28`) y `google-genai` (pide `httpx>=0.28.1`). El runtime es compatible — sólo es un problema de resolver. Instalá así en 3 pasos:

```bash
# 1) Todo menos supabase
pip install "fastapi[standard]>=0.115.0" "uvicorn[standard]>=0.30.0" \
  "authlib>=1.3.0" "python-jose[cryptography]>=3.3.0" "itsdangerous>=2.1.0" \
  "google-cloud-secret-manager>=2.20.0" "requests>=2.31.0" "gspread>=6.0.0" \
  "python-dotenv>=1.0.0" "python-dateutil>=2.9.0" "beancount>=3.2.0" \
  "google-genai>=1.75.0" "pytest>=8.0.0" "pytest-asyncio>=0.23.0"

# 2) Supabase sin sus deps (no fuerza downgrade de httpx)
pip install --no-deps "supabase>=2.7.0,<2.8.0"

# 3) Deps de supabase con versiones que NO arrastran pyiceberg
pip install "gotrue>=1.3,<3.0" "postgrest>=0.14,<0.17.0" \
  "realtime>=2.0.0,<3.0.0" "storage3>=0.5.3,<0.8.0" \
  "supafunc>=0.3.1,<0.6.0" deprecation

# 4) Forzar httpx 0.28+ (pip va a warnear sobre supabase, ignorá)
pip install "httpx>=0.28.1"
```

Verificación de runtime:
```bash
python -c "import supabase, httpx, beancount, fastapi; from google import genai; print('OK')"
```

### 2. Frontend — npm install

```bash
cd <project-root>/frontend
npm install
```

### 3. Variables de entorno

Copiá la plantilla:
```bash
cd <project-root>
cp .env.example .env
```

Completá los valores (las 17 variables). Fuentes:

| Variable | Fuente |
|---|---|
| `FRONTEND_URL` | `http://localhost:5173` (default Vite) |
| `BACKEND_URL` | `http://localhost:8000` (default uvicorn) |
| `JWT_SECRET` | generar fresh: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `JWT_ALGORITHM` | `HS256` |
| `JWT_EXPIRE_HOURS` | `8` |
| `RBAC_ROLE_MAPPING` | JSON: `{"tu-email@dominio.cl":"admin"}` |
| `ALLOWED_USERS` | Fallback legacy: `tu-email@dominio.cl:admin` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google Cloud Console → proyecto `family-office-Edu` → APIs & Services → Credentials → Web client 1 |
| `GOOGLE_APPLICATION_CREDENTIALS` | dejá `pipeline/config/serviceAccountKey.json` |
| `GOOGLE_SHEET_ID` | Render dashboard → laudus-backend → Environment |
| `LAUDUS_*`, `SUPABASE_*`, `GEMINI_API_KEY` | Render dashboard → laudus-backend → Environment |

### 4. Service Account JSON

El backend necesita `pipeline/config/serviceAccountKey.json` (es el credential file de Google referenciado por `GOOGLE_APPLICATION_CREDENTIALS`). El contenido vive en Render como env var `GOOGLE_SERVICE_ACCOUNT_JSON`. Para local:

```bash
mkdir -p pipeline/config
# Pegá el contenido de GOOGLE_SERVICE_ACCOUNT_JSON (desde Render dashboard) a:
#   pipeline/config/serviceAccountKey.json
# Es un JSON pretty-printed con private_key — está gitignored por seguridad.
```

### 5. Google OAuth — autorizar redirect local

En Google Cloud Console → proyecto `family-office-Edu` → APIs & Services → Credentials → Web client 1 → editar → "Authorized redirect URIs" → agregar:

```
http://localhost:8000/api/v1/auth/callback
```

Sin esto, el login Google va a fallar con `redirect_uri_mismatch` apenas intentes loguear.

---

## Troubleshooting

### Backend: `client_id=None` en el URL OAuth de Google

**Síntoma:** el browser muestra "OAuth client was not found" y el URL contiene `client_id=None`.

**Causa:** uvicorn arrancó sin cargar el `.env`. El código del backend hace `os.getenv("GOOGLE_CLIENT_ID")` pero **no llama a `load_dotenv()`** — en producción las vars vienen del environment del container; en local hay que pasarlas explícitamente.

**Fix:** usar el flag `--env-file .env` al arrancar uvicorn. Es lo que hace `run-backend.sh`. Si arrancás manualmente, el comando completo es:

```bash
uvicorn backend.main:app --reload --port 8000 --env-file .env
```

### Backend: `redirect_uri_mismatch` al hacer login

**Causa:** el callback `http://localhost:8000/api/v1/auth/callback` no está en la lista de Authorized redirect URIs del OAuth client.

**Fix:** agregalo en Google Cloud Console (ver paso 5 del setup). Cambios pueden tardar hasta 5 min en propagar.

### `pip install -r backend/requirements.txt` falla con `ResolutionImpossible`

**Causa:** conflicto declarativo `supabase` vs `google-genai` por `httpx`. Ver paso 1 del setup — instalá en 3 pasos manuales.

### Frontend: `npm run dev` arranca pero las llamadas API fallan

**Causa probable:** backend no está corriendo, o `VITE_API_URL` apunta a otro lado. El código hace fallback a `http://localhost:8000` si la var no está, lo cual es lo correcto para dev local — verificá que backend efectivamente corra en ese puerto.

### Build de `pyiceberg` falla con error de Visual C++

**Causa:** pip está agarrando una versión nueva de `storage3` (>=0.8) que depende de `pyiceberg`, que no compila en Python 3.14 sin Visual Studio C++ Build Tools.

**Fix:** pinear `storage3<0.8.0` (compatible con supabase 2.7.x). Ver paso 1 del setup, comando del paso 3.

---

## Notas operativas

- **`.env` y `pipeline/config/serviceAccountKey.json` están gitignored.** Nunca los commitees. Si los modificás, tu cambio se queda solo en tu máquina.
- **`run-backend.sh`** asume Git Bash en Windows. En Linux/Mac, cambiá `venv/Scripts/activate` por `venv/bin/activate` o usá el comando directo de uvicorn.
- **Frontend hot-reload**: Vite recarga automáticamente al guardar. Backend `--reload` también, pero a veces hay que reiniciar manual (ej: cambios en `__init__.py`).
- **Tests**: backend con `pytest` desde la raíz; frontend con `npm test` desde `frontend/`.
- **Diferencia con producción**: en Render, `entrypoint.sh` lee `GOOGLE_SERVICE_ACCOUNT_JSON` del environment y escribe `config/serviceAccountKey.json` al arrancar. En local hacemos el equivalente manual una sola vez (paso 4 del setup).
