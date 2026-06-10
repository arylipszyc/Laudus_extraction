# ADR-001 — Plan de cuentas: Beancount como fuente única editable

**Estado:** Aceptado (ratificado por Winston, 2026-06-10) · **Dirección aprobada por:** Ary (ver `sprint-change-proposal-2026-06-10.md`)
**Afecta:** Story 9.11 (scope ampliado), Story 10.3 (la desbloquea), Epic 10 (reporte)
**Autor:** Winston (System Architect)

---

## Contexto

La taxonomía contable (`Categoria1/2/3`) **no la provee Laudus** (solo número/nombre/notes — `bootstrap/sources.py:19`). Sale de un join con un plan de cuentas hoy **fragmentado en 3 fuentes**:

| Fuente | Estado | Consumidor |
|--------|--------|-----------|
| Supabase `plan_de_cuentas` | Dormido; marcado deprecación en 9.11 | nadie en prod |
| `ledger/accounts.beancount` (metadata `Open`) | Generado 1 vez desde Supabase por `generate_accounts.py` | dashboard (BQL) |
| Columnas `Categoria*` de `ledger_final` (Sheets) | Live (join externo) | reporte (SheetsRepository) |

**Defecto que lo gatilla:** una cuenta creada nueva en Laudus no está en el plan → llega con `Categoria` vacía → desaparecía del reporte en silencio (mitigado interinamente por Story 10.2). El prefijo del número de cuenta determina `Cat1`/`Cat2` (1:1 verificado) pero **no `Cat3`** (rubro fino → requiere criterio humano).

**Hallazgo clave:** la arquitectura de Epic 9 **ya anticipó** este flujo. `ledger/main.beancount` incluye `imports/_new-accounts-pending.beancount` (cuarentena) y `manual/*.beancount` (zona curada por humano). El importer (`pipeline/importers/laudus_run.py` + `writers/beancount_writer.py`) ya **detecta cuentas desconocidas y emite un `open` tentativo** en la cuarentena, con JEs tag `#pending-account`, hasta que se **promueven** con su Cat1/2/3. Ya existen lock de filesystem (`.import.lock`), commit+push a git (`git_commit_push`) y validación `bean-check` (Story 9.0).

## Decisión

1. **Beancount es la fuente única de verdad del plan de cuentas y su taxonomía.** Es la dirección ya implícita en Epic 9; se ratifica explícitamente. Supabase `plan_de_cuentas` se depreca en 9.11. Las columnas `Categoria*` de `ledger_final` dejan de ser autoritativas cuando el reporte migre de Sheets a Beancount (flag `USE_BEANCOUNT_ENGINE_LEDGER=true`).

2. **Ciclo de vida de una cuenta nueva (ya andamiado):**
   - Importer (9.4) detecta cuenta desconocida → `open` tentativo en `_new-accounts-pending.beancount`, JEs con `#pending-account`.
   - **Story 10.3 = la promoción:** UI lista las cuentas pendientes; sugiere `Cat1`/`Cat2` por prefijo; el contador fija `Cat2`/`Cat3`; el endpoint escribe el `open` final + metadata `laudus_categoria1/2/3`, saca la entrada de cuarentena, corre `bean-check` y commitea a git — **reusando el lock + `git_commit_push` ya existentes**.

3. **Destino de escritura de la cuenta promovida** *(recomendación, confirmar al implementar 10.3):*
   - **Recomendado — zona `manual/`:** escribir a `ledger/manual/*.beancount` (zona humana, nunca regenerada) → cero riesgo de clobber, separación limpia generado/curado (Open/Closed).
   - Alternativa — append a `accounts.beancount` (lo que dice literal el comentario de la cuarentena): más simple pero mezcla generado+manual; seguro solo una vez retirada la generación.

4. **`generate_accounts.py` / Supabase:** al deprecar Supabase (9.11), el script pierde su fuente de taxonomía. Se **retira como paso de rutina**; se conserva solo como re-bootstrap documentado de disaster-recovery. `accounts.beancount` (baseline congelado) + `manual/` pasan a ser el SoT.

5. **Secuencia (dependencias):** el reporte (Epic 10) lee Sheets hoy; migra a leer categorías de Beancount cuando `USE_BEANCOUNT_ENGINE_LEDGER=true` (gated a 9.4 en prod + 9.11). **10.3 entrega valor pleno solo cuando el reporte lee la misma fuente a la que 10.3 escribe.** Orden: **10.2 ✅ → 9.4 prod + 9.11 (reporte sobre Beancount) → 10.3.** Mientras tanto, el guard interino (10.2) mantiene visible la plata de cuentas nuevas.

## Riesgos y trade-offs

- **`.beancount` como store escribible desde un endpoint:** aceptable a esta escala (2-3 usuarios, 1 worker uvicorn). Reusar el `.import.lock` existente; la promoción es una escritura chica y serializada (el cron sábado y la promoción humana toman el mismo lock → sin carrera).
- **git como mecanismo de escritura + audit log:** beneficio explícito de Epic 9; infra ya existe (`git_commit_push`, deploy key con write). El endpoint debe degradar con gracia si el push falla (escribe local, reintenta) — patrón que ya usa el importer.
- **`bean-check` antes de commitear es NO-NEGOCIABLE:** un `open` malformado rompería TODAS las queries del ledger. Reusar el validador de Story 9.0.
- **Limitación conocida (documentada en `pipeline/importers/README.md`):** al promover, las JEs viejas siguen apuntando a la cuenta de cuarentena hasta correr un **backfill**. 10.3 debe disparar/recomendar el backfill post-promoción.

## Consecuencias

- **9.11:** scope confirmado — deprecar Supabase + Sheets-as-SoT; Beancount autoritativo.
- **10.3:** desbloqueada una vez el reporte lee Beancount; diseño = promoción reusando cuarentena + lock + git + bean-check. Una decisión menor pendiente para su implementación: destino de escritura (recomendado `manual/`).
- **Sin trabajo nuevo de infra mayor:** el andamiaje (cuarentena, lock, git, bean-check, flag) ya existe; 10.3 lo orquesta.
