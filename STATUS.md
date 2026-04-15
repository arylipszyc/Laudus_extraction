# Project Status — LAUDUS_Backup

## Current Phase
Epic 3 — Dashboards Financieros Multi-Entidad: EN PROGRESO

## Last Updated
2026-04-14

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
- **Story 3.4** — Análisis Interactivo Ingresos/Gastos: deployed y estabilizado (2026-04-13)
- **Fix post-deploy** (2026-04-13 21:42): filtros de gráficos consistentes — tarjetas de totales reflejan drill-down; movimientos filtrados por período seleccionado

## Bug Fixes Aplicados (2026-04-12)
- `IncomeExpensesPage`: clasificación ingresos/gastos usa `Categoria1` del PlanCuentas + fallback por prefijo
- `IncomeExpensesPage`: nombres de cuenta desde `accountName` del ledger enriquecido
- `IncomeExpensesPage`: drill-down por cuenta implementado (click en fila expande movimientos con fecha)
- `FilterContext`: preset "Trimestre" cambiado a rolling 90 días (era trimestre calendario)
- `LedgerEntryRecord` schema (Pydantic + TypeScript): agrega `accountName`, `Categoria1`; default `currencycode='CLP'`

## Bug Fixes Aplicados (2026-04-13) — post-deploy Story 3.4
- **Filtro de entidad bug 1**: backend seleccionaba sheet `ledger_{entity}` separado; solo existe `ledger_eag`.
  Fix: siempre fetch desde EAG, filtro client-side por contenido de Categoria1.
- **Filtro de entidad bug 2**: `Categoria1` en el Sheet es TODO MAYÚSCULAS (`EGRESOS JOCELYN AVAYU DEUTSCH`).
  Fix: comparación case-insensitive en `filterByEntity` con `DAUGHTERS = ['JOCELYN', ...]`.
- **Filtro de entidad bug 3**: `getLedgerCategory` no reconocía "egreso" (español para egresos/expenses).
  Fix: keyword "egreso" agregado, `Categoria2` como tercer parámetro de fallback.
- **Pie chart**: mostraba Cat1 (1 sola categoría por entidad) — click no tenía efecto visible.
  Fix: `buildPieDataByCat2` agrupa por Categoria2 → EAG gastos muestra 4 departamentos reales.
- **Pie drill-down**: click en Cat2 → pie cambia a Cat3 para esa Cat2; click Cat3 → toggle filtro.
  Botón "Volver" para subir nivel. Estado de drill en IncomeExpensesPage (para reset global).
- **Bar chart click**: Recharts v3 `Bar onClick` con `.payload` unreliable.
  Fix: `BarChart onClick` con `activeIndex` → `data[activeIndex].period`.
- **Totales cards**: usaban `allRecords` (sin filtro). Fix: usan `periodFiltered` → reactivos al filtro de período.
- **54 tests** en Vitest (ledgerAnalytics + useChartFilters)

## In Progress
- Nada en código. Phase 2 architecture completa.

## Phase 2 Architecture — Completada (2026-04-14)

Epic 4 (Ingesta de Cartolas) y Epic 5 (Categorización) diseñados con Winston. Ver `architecture.md` sección "Phase 2 Architecture: Epic 4 & 5".

**Decisiones clave:**
- Scope: solo tarjetas de crédito EAG (BCI, Santander, otros incl. USD). Cuentas corrientes diferidas.
- Storage híbrido: ERP data sigue en Sheets (`SheetsRepository` intocable); cartola data va a Supabase (`SupabaseRepository` nuevo)
- Gemini: PDF extraction sin config por banco; single integration point en `gemini_client.py`
- Categorización 2 etapas: historical match primero → Gemini fallback (elige de 85 cuentas fijas)
- Dashboard explosion: CC payment entries de Laudus se reemplazan por cartola_transactions cuando batch disponible
- CC identification: SIEMPRE por Cat2/Cat3 — NUNCA por accountName string matching

**⚠️ Prerequisito bloqueante para Epic 4:**
Ary debe actualizar taxonomía Cat2/Cat3 en Laudus/Google Sheets para marcar claramente las cuentas de tarjetas de crédito ANTES de que Dev empiece implementación.

## Next Steps
- [ ] Ary actualiza Cat2/Cat3 taxonomy en Laudus (prerequisito bloqueante)
- [ ] SM genera stories para Epic 4 (Ingesta) y Epic 5 (Categorización)
- [ ] Story 3.5 — DIFERIDA a Phase 2 (ya cubierta por Epic 4/5 architecture)

## Stack Decidido
- Backend: FastAPI (Python) + authlib + python-jose + itsdangerous
- Frontend: React + Vite + TypeScript + Tailwind v3 + shadcn/ui + Recharts v3 + React Query v5
- Auth: Google OAuth + JWT httpOnly cookies (access_token)
- Storage Fase 1: Google Sheets (Repository pattern — DataRepository ABC)
- Hosting: Google Cloud Run → migrado a Render (free tier, Docker + Static Site)

## Recharts v3 — Lecciones Aprendidas
- `BarChart onClick`: recibe `MouseHandlerDataParam` con `activeIndex` (sin `activePayload`)
- `Bar onClick`: recibe `BarRectangleItem` con `payload?: any` (unreliable en v3)
- `Pie onClick`: recibe datum directamente, `entry.name` funciona
- `Categoria1` en ledger_eag viene en MAYÚSCULAS desde Laudus

## Estructura Real de ledger_eag (confirmada leyendo el Sheet)
Categorias EAG: `ACTIVO EAG`, `GASTOS - EGRESOS`, `INGRESOS`, `PASIVO`
Categorias hijas: `DISPONIBLE/EGRESOS/INGRESOS + [NOMBRE] AVAYU DEUTSCH` (×4 hijas)
Cat2 de GASTOS - EGRESOS: `Casa Sur`, `DEPARTAMENTO SANTIAGO`, `DEPARTAMENTO MIAMI`, `GASTOS PERSONALES`
Cat3: múltiples por Cat2 (Sueldos, Mantenciones, Vehículos, Salud, etc.)

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
- Story 3.5 diferida: tarjetas de crédito mal clasificadas como gastos en Laudus. Fix correcto requiere
  cartolas bancarias (Phase 2). Reclasificar solo en frontend descuadraría la contabilidad.
