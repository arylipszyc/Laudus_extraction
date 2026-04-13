# Project Status — LAUDUS_Backup

## Current Phase
Epic 3 — Dashboards Financieros Multi-Entidad: EN PROGRESO

## Last Updated
2026-04-13

## Completed
- Initial PRD drafted and validated (2026-04-06)
- Project Command module (poc) built and installed
- PRD fixes: FR31 reescrito con criterio testeable (2026-04-08)
- Revisión de código existente: pipeline Python evaluado
- Arquitectura completa validada (2026-04-08)
- Epics & Stories: 8 epics, 13 MVP stories escritas con BDD ACs (2026-04-09)
- Sprint planning: sprint-status.yaml generado (2026-04-09)
- **Epic 1** — Plataforma Base y Autenticación: DONE (stories 1.1–1.5)
- **Epic 2** — Sincronización ERP: DONE
- **Story 3.1** — Dashboard API Endpoints backend: DONE
- **Story 3.2** — Filtros de Entidad y Fecha (frontend): deployed
- **Story 3.3** — Dashboard Activos/Pasivos e Ingresos/Gastos: deployed
- **CD configurado en Render** (2026-04-12):
  - Frontend: https://laudus-frontend.onrender.com
  - Backend: https://laudus-backend.onrender.com
  - Auto-deploy en push a main

## Bug Fixes Aplicados (2026-04-12)
- `IncomeExpensesPage`: clasificación ingresos/gastos usa `Categoria1` del PlanCuentas + fallback por prefijo
- `IncomeExpensesPage`: nombres de cuenta desde `accountName` del ledger enriquecido
- `IncomeExpensesPage`: drill-down por cuenta implementado (click en fila expande movimientos con fecha)
- `FilterContext`: preset "Trimestre" cambiado a rolling 90 días (era trimestre calendario — coincidía con "Mes" en abril)
- `LedgerEntryRecord` schema (Pydantic + TypeScript): agrega `accountName`, `Categoria1`; default `currencycode='CLP'`

## In Progress
- Verificar en producción que nuevo dashboard Ingresos/Gastos (3.4) clasifica y filtra correctamente.

## Completed (additional)
- **Story 3.4** — Análisis Interactivo Ingresos/Gastos: deployed (2026-04-13)
  - Pie charts de composición por Categoria1 (clickables)
  - Bar chart de evolución mensual (clickable)
  - Filtros acumulativos por gráfico con reset
  - Drill-down jerárquico: Categoria1 → cuenta → movimientos
  - 43 tests (Vitest instalado por primera vez)

## Next Steps
- [ ] Story 3.5 — DIFERIDA a Phase 2 (tarjetas de crédito requieren cartolas, no disponibles en MVP)
- [ ] Epic 3 completo — evaluar inicio de Epic 4 (Phase 2) o priorizar mejoras

## Stack Decidido
- Backend: FastAPI (Python) + authlib + python-jose + itsdangerous
- Frontend: React + Vite + TypeScript + Tailwind v3 + shadcn/ui + Recharts + React Query v5
- Auth: Google OAuth + JWT httpOnly cookies (access_token)
- Storage Fase 1: Google Sheets (Repository pattern — DataRepository ABC)
- Hosting: Google Cloud Run → migrado a Render (free tier, Docker + Static Site)

## Artefactos
- PRD: `_bmad-output/planning-artifacts/prd.md`
- Arquitectura: `_bmad-output/planning-artifacts/architecture.md`
- Epics: `_bmad-output/planning-artifacts/epics.md`
- Sprint status: `_bmad-output/implementation-artifacts/sprint-status.yaml`
- Stories: `_bmad-output/implementation-artifacts/`

## Blockers
- Google OAuth requiere credenciales reales en .env para pruebas end-to-end
  - GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, ALLOWED_USERS

## Notes
- Invocar Moishe con /poc-agent-moishe al inicio de cada sesión
- Código existente (sync.py, laudus_service.py, models.py, gspread_utils.py) se reutiliza íntegro
- `ledger_{entity}` es copia de `ledger_final` — tiene `accountName`, `Categoria1` pero NO `currencycode`
