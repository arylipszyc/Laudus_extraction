# Onboarding contador — Fava (Story 9.3)

Fava es la UI contable hosteada que lee el ledger Beancount de producción. Permite ver Income
Statement, Balance Sheet, Trial Balance, Net Worth, el workbench BQL y hacer drill-down — y
**editar el ledger de forma segura** (con el wrapper `bean-check` de Story 9.0 que revierte un
edit que rompa la contabilidad).

> **Acceso:** la URL y las credenciales se entregan **por canal seguro, fuera del repo**.
> Único usuario (basic auth, env `FAVA_BASIC_AUTH_USER`). **La family NO accede a Fava** (Q5).

## Qué podés hacer

- **Income Statement / Balance Sheet / Trial Balance / Net Worth:** reportes estándar de Beancount.
- **BQL workbench:** consultas tipo `SELECT account, sum(position) WHERE ... GROUP BY account`.
- **Drill-down:** click en una cuenta → sus movimientos.
- **Editar:** el editor de Fava está habilitado (`EDIT_HOOK_ENABLED=true`). Al guardar, el wrapper
  bean-check valida el cambio: si queda válido, persiste + se commitea/pushea al repo; si rompe la
  contabilidad, **se revierte** y verás el error. **Siempre editá vía Fava UI — nunca por GitHub/PR**
  (Q2). Los datos se refrescan solos ≤ 60s tras cada import (git pull periódico + watchfiles).

## ⚠️ Pre-condición ANTES de operar cartolas: poblar `bank_account_last4`

El bootstrap (Story 9.1) dejó `bank_account_last4` en **null** para las 47 cuentas bancarias (el
dato vivía en Google Sheets, no en Supabase). Story 9.5 **exige** ese campo para validar uploads de
cartola. Antes de subir la primera cartola hay que poblarlo (≈30 min, una vez):

1. En Fava, abrí el editor sobre `accounts.beancount`.
2. Por cada `open` de una cuenta bancaria (las que tienen `bank_account_id`), agregá la metadata:
   ```beancount
   bank_account_last4: "1234"
   ```
   con los últimos 4 dígitos reales de la cuenta/tarjeta.
3. Fuente del dato: la pestaña `Bancos` de Google Sheets (que se deprecó en Story 9.11 — exportala
   o consultala antes de que se apague del todo).
4. Guardá: bean-check valida que el ledger siga sano.

> **Nota técnica (post-poblado):** con los `last4` reales conviene re-evaluar re-habilitar la
> detección server-side de "cuenta equivocada" (last4 del índice vs last4 del PDF). Story 9.5h la
> neutralizó porque el smoke usaba `last4="9999"` dummy (100% de PARSE_AMBIGUOUS espurios). Ver
> `9-5h-validators-deterministas-flash-3-5.md` → Review Findings + TODO en `gemini_client.py`.

## Deploy (referencia — handoff a Ary)

Servicio Render `laudus-fava` (web service, Docker = `Dockerfile.fava`), persistent disk en
`/ledger` (≥1GB). Env vars:

| Var | Para qué |
|---|---|
| `BEANCOUNT_REPO_URL` | repo del ledger a clonar/pullear |
| `BEANCOUNT_DEPLOY_KEY` | SSH key (write, para que el editor commitee/pushee) |
| `FAVA_BASIC_AUTH_USER` / `FAVA_BASIC_AUTH_PASSWORD` | basic auth (único usuario) |
| `EDIT_HOOK_ENABLED` | `true` (9.0 done) → editor activo; `false` → Fava read-only |
| `PORT` | inyectada por Render (nginx escucha ahí) |

**Smoke post-deploy:** (1) URL sin auth → 401; (2) con auth → home de Fava + sidebar muestra
"LAUDUS — EAG Family Office"; (3) Trial Balance con datos; (4) BQL `SELECT count(*)` > 0;
(5) un edit válido persiste y uno inválido se revierte.

## AC8 — cumplido cuando Ary haya

1. Operado Fava ≥1 ciclo de import + revisión (auto-onboarding como contador interino).
2. Poblado `bank_account_last4` en las 47 cuentas (pre-condición de Story 9.5).

La sesión 1-1 con un contador externo queda diferida hasta asignar la persona — no bloquea el deploy.
