---
story: 9.3
title: Fava deploy en Render con basic auth
status: ready-for-dev
epic: 9
depends_on: [9.0, 9.1]
blocks: []
---

# Story 9.3 — Fava deploy en Render

## User Story

As the contador,
I want a hosted Fava UI accessible behind basic auth that reads the production `ledger/` and lets me edit the ledger safely (with `bean-check` revert protection from Story 9.0),
So that I have a professional accounting workflow (Income Statement, Balance Sheet, BQL workbench, drill-down, edit) without needing local setup or git access.

## Context

F2 del plan de migración (`architecture-c4.md` §7.3 + §6). Crear un servicio Render web nuevo (`laudus-fava`) con:
- Imagen Docker custom: `python:3.12-slim` + `pip install fava beancount` + entrypoint con basic auth proxy.
- Persistent disk montado en `/ledger` con `git pull` periódico (cada 60s) para refresh.
- Editor de Fava habilitado **con el wrapper `bean-check` de Story 9.0** ya en lugar.
- Basic auth: un único par usuario/password (Q5 — la family NO accede a Fava).

## Acceptance Criteria

**AC1 — Servicio Render `laudus-fava` deployado**

**Given** el repo tiene un `Dockerfile.fava` + entry definido
**When** el servicio se despliega en Render como web service
**Then** la URL pública responde HTTP 200 sobre la home de Fava
**And** la URL es accesible sólo bajo HTTPS
**And** el sidebar de Fava muestra el nombre del ledger (option `title` = "LAUDUS — EAG Family Office")

---

**AC2 — Basic auth gate**

**Given** las env vars `FAVA_BASIC_AUTH_USER` y `FAVA_BASIC_AUTH_PASSWORD` están set en Render
**When** un usuario accede a la URL sin auth header válido
**Then** recibe HTTP 401 con `WWW-Authenticate: Basic realm="laudus-fava"`
**And** después de proveer credenciales válidas → accede a Fava normal
**And** después de proveer credenciales inválidas → permanece en HTTP 401

---

**AC3 — Persistent disk con `ledger/` actualizado**

**Given** el servicio tiene un persistent disk montado en `/ledger`
**When** el servicio inicia
**Then** ejecuta `git clone $BEANCOUNT_REPO_URL /ledger` si no existe, o `cd /ledger && git pull` si existe
**And** un proceso background corre `git pull` cada 60s para refresh
**And** Fava sirve sobre `/ledger/main.beancount`

---

**AC4 — Reload automático tras git pull**

**Given** el importer Laudus (Story 9.4) commitea+pusheó nuevos archivos `.beancount`
**When** el `git pull` periódico de `laudus-fava` los descarga
**Then** Fava detecta el cambio (`watchfiles`) y refleja las nuevas transactions en la UI sin restart
**And** un usuario en Fava ve los datos nuevos al refrescar (< 60s desde el push)

---

**AC5 — Editor habilitado con wrapper bean-check (DEP 9.0)**

**Given** Story 9.0 está done (wrapper bean-check funcionando) Y Fava está deployado
**When** el contador edita un archivo desde Fava UI
**Then** el wrapper de Story 9.0 se invoca sobre el cambio
**And** edits válidos persisten + push al repo (vía `git commit + push` post-validation)
**And** edits inválidos se revierten + log + mensaje al contador (AC1-AC5 de Story 9.0)
**And** si Story 9.0 NO está done todavía: el editor de Fava se DEPLOY DESHABILITADO (config `EDIT_HOOK_ENABLED=false`); deploy con editor pasa solo cuando 9.0 está done

---

**AC6 — RBAC: family NO accede a Fava**

**Given** Q5 cerrada — solo el contador accede a Fava
**When** alguien intenta autenticarse con credenciales de family (no del contador)
**Then** falla en HTTP 401 (basic auth gate no acepta otras credenciales)
**And** la documentación operativa deja explícito que `FAVA_BASIC_AUTH_USER` es el único usuario posible

---

**AC7 — Audit log de acceso a Fava**

**Given** el servicio Fava recibe requests autenticadas
**When** un request entra
**Then** se loguea: timestamp ISO 8601, basic auth user, request method, path, response status (en stdout, capturado por Render logs)
**And** los logs son accesibles vía Render dashboard ≥ 7 días para review

---

**AC8 — Onboarding doc para el contador interino (Ary) + pre-condición de `bank_account_last4`**

> Ajuste 2026-04-30: contador real sin asignar. Ary actúa como **contador interino** hasta que se asigne uno externo. No bloquea el deploy.
> Ajuste 2026-05-05 (Flag 6): el bootstrap de Story 9.1 deja `bank_account_last4` en null para las 47 cuentas (el dato vive en Google Sheets, no en Supabase, y el bootstrap no lee Sheets). Ary debe poblarlas manualmente vía Fava antes de operar cartolas.

**Given** el servicio está deployado
**When** se entrega documentación inicial
**Then** existe `docs/contador-onboarding-fava.md` con:
  - URL del servicio + credenciales (entrega manual, NO en el repo)
  - Walkthrough Fava: Income Statement, Balance Sheet, Trial Balance, Net Worth, BQL workbench, drill-down
  - Cómo editar (con explicación del wrapper bean-check + qué hacer si revert)
  - Workflow: "siempre edits vía Fava UI — nunca PR/GitHub directo" (Q2 reforzada)
  - **Sección "Pre-condición antes de operar cartolas":** instrucciones para poblar manualmente `bank_account_last4: "XXXX"` en cada `open` directive bancaria de `accounts.beancount` (las 47 cuentas) — fuente del dato: Google Sheets tab `Bancos` (que será deprecated en Story 9.11). Estimado ~30 min trabajo único.
**And** AC8 se considera **cumplido cuando Ary haya:**
  1. Operado Fava al menos 1 ciclo de import + revisión (auto-onboarding como contador interino)
  2. Poblado `bank_account_last4` en las 47 cuentas bancarias (pre-condición para que Story 9.5 valide uploads)
**And** la sesión 1-1 con un contador externo queda diferida hasta que Ary asigne la persona — no bloquea esta story ni el deploy

---

## Tasks / Subtasks

- [ ] Task 1: `Dockerfile.fava`
  - [ ] Base: `python:3.12-slim`
  - [ ] Install: `fava>=1.27`, `beancount>=3.2`, `git`
  - [ ] Setup: agregar entrypoint `entrypoint-fava.sh` que: `git clone || git pull` → start basic auth proxy → start Fava
  - [ ] Expose: `$PORT` (Render-injected)

- [ ] Task 2: Basic auth proxy
  - [ ] Opción A: nginx sidecar con `htpasswd` generado desde env vars en startup
  - [ ] Opción B: Python proxy minimalista (`starlette` + middleware basic auth) reverse-proxying a Fava local
  - [ ] Recomendación: A (nginx — más estándar, menos código). Si Render bloquea sidecars en single web service, fallback B.
  - [ ] Validar: requests sin auth → 401; con auth válida → pasa a Fava; con inválida → 401

- [ ] Task 3: Git sync background process
  - [ ] Script `entrypoint-fava.sh` que arranca un loop `while sleep 60; cd /ledger && git pull --quiet || true; done` en background
  - [ ] Variables: `BEANCOUNT_REPO_URL`, `BEANCOUNT_DEPLOY_KEY` (read-only key acá; write key se usa solo en Story 9.4)
  - [ ] Asegurar que `git pull` no rompe el ledger en uso (Fava `watchfiles` detecta el cambio post-pull)

- [ ] Task 4: Editor hook integration (DEP 9.0)
  - [ ] Config flag `EDIT_HOOK_ENABLED` env var (default `false` hasta que 9.0 esté done)
  - [ ] Si `true`: cargar la opción/extension/watcher definida por Story 9.0
  - [ ] Si `false`: Fava se sirve con `--read-only` o el flag equivalente que deshabilita el editor
  - [ ] Verificar que el switch funciona: con `false` el botón de editar de Fava no aparece o devuelve 403

- [ ] Task 5: Render service config
  - [ ] Crear servicio `laudus-fava` en Render (web service, docker)
  - [ ] Configurar persistent disk montado en `/ledger`, ≥ 1GB
  - [ ] Env vars: `BEANCOUNT_REPO_URL`, `BEANCOUNT_DEPLOY_KEY`, `FAVA_BASIC_AUTH_USER`, `FAVA_BASIC_AUTH_PASSWORD`, `EDIT_HOOK_ENABLED`
  - [ ] Health check path: `/` (Fava responde con auth challenge — eso cuenta como "alive")

- [ ] Task 6: Documentación operativa (AC8)
  - [ ] Escribir `docs/contador-onboarding-fava.md` (ver AC8 para contenido)
  - [ ] Walkthrough con screenshots básicos opcionales (no bloquea deploy)
  - [ ] Disclaimer sobre Q2: el contador NO usa GitHub, todo vía Fava
  - [ ] Sección dedicada "Pre-condición: poblar `bank_account_last4` en las 47 cuentas" con paso-a-paso vía Fava editor (referenciar Story 9.5 que valida ese campo en uploads)
  - [ ] **Al poblar los last4 reales:** re-evaluar re-habilitar la detección server-side de cuenta-equivocada (last4-índice vs last4-PDF). Story 9.5h la neutralizó porque el tooling de smoke usaba `last4="9999"` dummy → 100% de PARSE_AMBIGUOUS espurios; con last4 reales el check vuelve a tener señal. Ver `9-5h-validators-deterministas-flash-3-5.md` → Review Findings (Decision) + TODO en `gemini_client.py` `_build_prompt`.

- [ ] Task 7: Smoke test post-deploy
  - [ ] Acceder a la URL → 401
  - [ ] Auth válida → Fava home + sidebar muestra nombre del ledger
  - [ ] Trial Balance carga + tiene datos
  - [ ] BQL workbench: `SELECT count(*) FROM #` → número > 0
  - [ ] Editor: si `EDIT_HOOK_ENABLED=true`, verificar que un edit válido persiste, uno inválido se revierte

---

## Dev Notes

### Input autoritativo

`architecture-c4.md` §5.4 (Fava endpoint y auth) + §6.1 (Servicios Render) + §6.2 (Storage del ledger). Q5 cierre: basic auth, family NO accede. Q2 cierre: editor habilitado con wrapper bean-check.

### Persistent disk vs ephemeral

Render web services por defecto son ephemeral. Necesitamos persistent disk para que `git clone /ledger` no se reejecute en cada deploy. Costo ~$1-2/mes por GB. Documentar en cierre del story.

### No usar OAuth proxy

Q5 cerró basic auth. NO implementar Google OAuth proxy en esta story aunque sea más sofisticado — es overkill para 1 usuario y agrega complejidad de deploy. Si en el futuro family accede a Fava, abrir story de migración a OAuth.

### Out of scope

- Onboarding real con el contador (sesión 1-1) — Ary la dispara post-deploy.
- Cambios al wrapper bean-check (Story 9.0).
- Cualquier cambio al thin API o frontend LAUDUS.

### Project structure

```
Dockerfile.fava                           # NEW
entrypoint-fava.sh                        # NEW
nginx-fava.conf                           # NEW (si Opción A)
docs/
  contador-onboarding-fava.md             # NEW
```

### References

- [Source: architecture-c4.md §5.4, §6.1, §6.2]
- [Source: architecture-c4.md §7.3 — Plan F2]
- [Source: bob-x-moishe-epic9-2026-04-30.md — Q2, Q5 cierre + Flag 6 (last4 vive en Sheets, pre-condición en este AC8)]
- [Source: 9-5-pdf-upload-gemini-json-canonico.md — consume `bank_account_last4` en validación AC1]
- [External: https://beancount.github.io/fava/ — Fava docs]
