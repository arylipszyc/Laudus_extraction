# Project Status — LAUDUS_Backup

## Current Phase
Epic 1 — Plataforma Base y Autenticación: EN PROGRESO

## Last Updated
2026-04-10

## Completed
- Initial PRD drafted and validated (2026-04-06)
- Project Command module (poc) built and installed
  - Moishe (poc-agent-moishe) live at ~/.claude/skills/poc-agent-moishe/
  - Global sanctum initialized at C:\dev\bmad-workspace\_moishe\
- PRD fixes: FR31 reescrito con criterio testeable (2026-04-08)
- Revisión de código existente: pipeline Python evaluado, Pipfile actualizado con dependencias
- Arquitectura completa validada (2026-04-08)
- Epics & Stories: 8 epics, 13 MVP stories escritas con BDD ACs (2026-04-09)
- Sprint planning: sprint-status.yaml generado (2026-04-09)
- **Story 1.1** — Backend FastAPI scaffold + Repository pattern → review (2026-04-09)
- **Story 1.2** — Frontend React + Vite scaffold → review (2026-04-09)
- **Story 1.3** — Google OAuth Authentication → review (2026-04-10)
  - 27/27 backend tests passing
  - Frontend: 88 módulos, 0 errores, build 533ms
  - authlib OAuth + python-jose JWT + httpOnly cookies
  - ALLOWED_USERS role assignment via env var

## In Progress
- **Story 1.5** — Audit Log + Backup + Cloud Run: story creada, `ready-for-dev`

## Completed (esta sesión)
- **Story 1.4** — RBAC: implementada, code review completado, status `done`

## Next Steps
- [ ] Story 1.5: Audit Log + Backup + Cloud Run — implementar con Amelia (`_bmad-output/implementation-artifacts/1-5-audit-log-backup-workflow-y-cloud-run-deployment.md`)
- [ ] Luego: Epic 2 (Sync API, Incremental Sync, Backfill UI)
- [ ] Story 1.5: Audit Log, Backup Workflow y Cloud Run Deployment
- [ ] Luego: Epic 2 (Sync API, Incremental Sync, Backfill UI)
- [ ] Luego: Epic 3 (Dashboards financieros)

## Stack Decidido
- Backend: FastAPI (Python) + authlib + python-jose + itsdangerous
- Frontend: React + Vite + TypeScript + Tailwind v3 + shadcn/ui + Recharts + React Query v5
- Auth: Google OAuth + JWT httpOnly cookies (access_token)
- Storage Fase 1: Google Sheets (Repository pattern — DataRepository ABC)
- Hosting Fase 1: Google Cloud Run (scale to zero, ~$0/mes)

## Artefactos
- PRD: `_bmad-output/planning-artifacts/prd.md`
- Arquitectura: `_bmad-output/planning-artifacts/architecture.md`
- Epics: `_bmad-output/planning-artifacts/epics.md`
- Sprint status: `_bmad-output/implementation-artifacts/sprint-status.yaml`
- Stories: `_bmad-output/implementation-artifacts/1-*.md`

## Blockers
- Google OAuth requiere credenciales reales en .env antes de poder probar end-to-end
  - GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, ALLOWED_USERS
  - Redirect URI: `http://localhost:8000/api/v1/auth/callback` en Google Cloud Console

## Notes
- Invocar Moishe con /poc-agent-moishe al inicio de cada sesión
- Código existente (sync.py, laudus_service.py, models.py, gspread_utils.py) se reutiliza íntegro
- itsdangerous agregado a requirements.txt y Pipfile (requerido por SessionMiddleware de authlib)
- LoginPlaceholder.tsx se conservó — Login.tsx es el reemplazo activo en App.tsx
