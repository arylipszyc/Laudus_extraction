# EAG Family Office

Plataforma que devuelve visibilidad financiera al head de un family office multi-entidad: automatiza el pipeline desde sistemas fuente (Laudus ERP + cartolas bancarias PDF) hacia dashboards interactivos, con categorización asistida por LLM, reconciliación mensual y canal de comunicación entre owner y contador.

**Stack:** FastAPI + React (Vite) + Beancount (ledger) + Supabase (Postgres) + Google OAuth + Gemini (parsing PDF). Deploy en Render.

**Estado:** post-pivot a Beancount (Epic 9, abr–may 2026). Ver [docs/archive/README-v1-sync.txt](docs/archive/README-v1-sync.txt) para la primera versión (script `sync.py` Laudus → Google Sheets, Mar 2026).

---

## Quick start

Setup y arranque del stack local: **[docs/local-dev.md](docs/local-dev.md)**.

TL;DR si ya tenés el setup:

```bash
# Terminal 1
./run-backend.sh                    # uvicorn :8000 con --env-file .env

# Terminal 2
cd frontend && npm run dev          # Vite :5173
```

---

## Documentación

### Operativa

- **[docs/local-dev.md](docs/local-dev.md)** — setup desde cero, troubleshooting (conflictos `httpx`/`supabase`, OAuth `redirect_uri_mismatch`, `--env-file`).
- **[docs/rbac-3-roles.md](docs/rbac-3-roles.md)** — matriz autoritativa de roles (`family` / `contador` / `admin`), email→role mapping vía `RBAC_ROLE_MAPPING`, defense-in-depth.

### Planning artifacts (`_bmad-output/planning-artifacts/`)

- **[prd.md](_bmad-output/planning-artifacts/prd.md)** — Product Requirements Document (alcance, FRs, NFRs).
- **[architecture.md](_bmad-output/planning-artifacts/architecture.md)** — diseño de solución.
- **[architecture-c4.md](_bmad-output/planning-artifacts/architecture-c4.md)** — vistas C4.
- **[epics.md](_bmad-output/planning-artifacts/epics.md)** — épicas y stories.
- **[research-beancount-pivot-2026-04-30.md](_bmad-output/planning-artifacts/research-beancount-pivot-2026-04-30.md)** — research que motivó el pivot a Beancount.

### Histórico

- **[docs/archive/README-v1-sync.txt](docs/archive/README-v1-sync.txt)** — README original (v1: `sync.py` Laudus → Sheets).

---

## Estructura del repo

```
backend/        FastAPI app (auth, RBAC, endpoints, sync, parsing PDF Gemini)
frontend/       React + Vite (dashboards, drill-down, reconciliación)
pipeline/       Laudus client + sync legacy + service account config
ledger/         Beancount files (canonical accounting source)
supabase/       Migrations
samples/        Sample data
design-artifacts/, _bmad/, _bmad-output/  artefactos BMAD (planning, coord, stories)
docs/           Documentación operativa
```
