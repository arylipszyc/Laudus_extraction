# Rollback — Migración de bank-accounts a Beancount (Story 9.14)

**Objetivo:** revertir el wiring de `/api/v1/bank-accounts/` de Beancount a Supabase si algo
se rompe post-migración. **Ejecutable en < 30 minutos.**

## Qué cambió (2026-06-17)

`GET/POST/PATCH /api/v1/bank-accounts/` ahora lee/escribe la metadata bancaria de los `open`
de `ledger/accounts.beancount` (modelo unificado 9.1) en vez de la tabla Supabase
`bank_accounts`. Archivos tocados:

- `backend/app/api/v1/bank_accounts/{router,service,schemas}.py`
- `backend/app/services/beancount_promote.py` (helper de escritura reusable, +editores de bloque)
- `backend/app/repositories/supabase_repository.py` (métodos de bank-accounts marcados deprecados, sin borrar)

## Rollback de código (≈ 10 min)

1. `git revert` del commit de 9.14 (o `git checkout <sha-previo> -- backend/app/api/v1/bank_accounts/`).
   El service vuelve a usar `SupabaseRepository`; el router deja de inyectar `LedgerService`.
2. Confirmar que `SUPABASE_URL` / `SUPABASE_KEY` siguen seteadas en Render (si NO se apagó Supabase,
   siguen ahí; si se apagó, ver paso de reactivación).
3. Redeploy del backend desde main.
4. Smoke: `GET /api/v1/bank-accounts/` devuelve la lista; `CartolaUploadPage` carga el dropdown.

## Reactivar Supabase (sólo si ya se apagó — AC5, ≈ 15 min)

> El apagado de Supabase es un **handoff manual a Ary** (AC5), no parte del deploy de código.
> Si todavía NO se apagó, este bloque no aplica.

1. Reactivar el proyecto Supabase standby desde el dashboard de Supabase.
2. Re-setear las env vars en Render (Dashboard → Environment): `SUPABASE_URL`, `SUPABASE_KEY`.
   (No están en `render.yaml` → se setean a mano.)
3. Reinstalar la dependencia si se removió: `supabase==2.5.0` en `backend/requirements.txt`.
4. Verificar que las tablas `bank_accounts` y `plan_de_cuentas` siguen pobladas (no se borraron al apagar).

## Nota — captura one-time del estado `active` (pre-apagado)

`active` era un constructo solo-Supabase; en Beancount se deriva de `open`/`close`. Hoy hay
**cero directivas `close`** en el ledger, así que toda cuenta migrada arranca `active=true`.
Antes de apagar Supabase, capturar las cuentas con `active=false` de la tabla viva
`bank_accounts` y emitir un `PATCH {id} {"active": false}` por cada una (escribe el `close`
correspondiente) para preservar el estado. Si no había ninguna inactiva, no hay nada que capturar.
