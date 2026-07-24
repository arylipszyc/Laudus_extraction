---
title: 'Fase 3 batch 3 — Robustez del pipeline de escritura (B5/B4/B8)'
type: 'bugfix'
created: '2026-07-06'
status: 'done'
baseline_commit: '74e3a19'
context:
  - '{project-root}/_bmad-output/planning-artifacts/review-estabilidad-performance-2026-07-06.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Tres agujeros de robustez en el pipeline de escritura del ledger: (B5) el lock de import es TOCTOU (dos procesos pueden "adquirirlo" a la vez y dos waiters pueden robar el mismo lock stale) y su stale-timeout de 300s es más corto que un backfill legítimo → robo de lock con el holder VIVO = dos escritores concurrentes sobre el ledger; además el `git reset --hard` del sync corre FUERA del lock y puede pisar una escritura concurrente. (B4) la clave de dedup de discrepancias incluye `batch_id` (nuevo en cada upload) → re-subir la misma cartola duplica todas las discrepancias abiertas e infla los counts del dashboard. (B8) la paginación de Laudus es `while True` sin tope (una API que repite página = loop infinito sosteniendo el lock) y `login()` traga toda excepción (el error real se pierde tras un genérico "No hay token").

**Approach:** Lock atómico (`os.open(O_CREAT|O_EXCL)`) + heartbeat que renueva el mtime mientras el holder vive; el refresh del clon se muda dentro del lock con el patrón callback que `beancount_promote` ya usa; dedup por identidad del contenido (`bank_account_id, year_month, line_no, je_id, state`); tope de páginas + detección de página que no avanza; `login()` propaga la causa real.

## Boundaries & Constraints

**Always:** el context manager `acquire_lock` mantiene su firma/semántica pública (los 8 call-sites y sus tests siguen sin cambios); idempotencia intra-batch del dedup se preserva (mismo batch re-corrido → 0 nuevas); el heartbeat muere SIEMPRE al liberar el lock (sin threads huérfanos); suite backend verde, 0 regresiones.

**Ask First:** cambiar la semántica de espera del lock (timeout/poll); tocar el shape del JSONL de discrepancias.

**Never:** locks distribuidos/DB; migrar/reescribir el JSONL existente (las entradas legacy quedan como están); tocar frontend; el resto de Fase 3 (D6/D7/categorización async).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Dos adquisiciones simultáneas | 2 threads compiten por el lock libre | exactamente UNO adquiere (O_EXCL); el otro espera/timeout | LockTimeout como hoy |
| Lock stale (holder muerto) | mtime > max_age | un waiter lo remueve y adquiere; si DOS waiters compiten post-remove, solo uno gana (O_EXCL en el retry-loop) | — |
| Holder vivo con operación larga | backfill >300s dentro del lock | heartbeat renueva mtime cada ~60s → nunca es "stale" → nadie lo roba | — |
| Liberación | éxito o excepción | heartbeat detenido + lock unlink (finally) | — |
| Sync con reset | `_run_laudus_import` | fetch+reset --hard corren DENTRO del lock (callback `refresh_clone` de `run_import`, patrón beancount_promote); una categorización concurrente ya no puede ser pisada | refresh falla → warning y sigue (best-effort actual) |
| Re-upload de la misma cartola | mismo mes/cuenta, batch_id NUEVO, mismas líneas | 0 discrepancias nuevas (dedup por contenido, no por batch) | — |
| Mismo batch re-corrido | idempotencia AC7 | 0 nuevas (igual que hoy) | — |
| Discrepancia legacy sin year_month | entrada pre-6.5b en el JSONL | su clave lleva year_month=None → un re-upload moderno del mismo mes NO colisiona → posible dupe UNA vez (residual aceptable, documentado) | — |
| Línea re-extraída con line_no distinto | Gemini re-numera en el re-upload | dupe posible (residual conocido: la identidad de línea depende de la extracción) | — |
| API repite página | `nextPage` no avanza / hasMore eterno | raise tras detectar page-param repetido o al llegar a MAX_PAGES | run_import → failed |
| login falla | credenciales malas / red | excepción propaga con la causa real (antes: None → "No hay token") | run_import → failed con el error real |

</frozen-after-approval>

## Code Map

- `pipeline/importers/laudus_run.py:52-76` — `acquire_lock`: O_CREAT|O_EXCL en retry-loop + thread daemon heartbeat (touch mtime cada ~60s, `threading.Event` para pararlo en el finally). Beneficia a los 8 call-sites (transactions, promote, cartola_pdf, reconcile ×2, tc_correction, run_import)
- `pipeline/importers/laudus_run.py:255-300` — `run_import(..., refresh_clone: Callable | None = None)`: llamarlo tras adquirir el lock (patrón `beancount_promote.py:181-203`)
- `backend/app/api/v1/sync/service.py:141-149` — `_run_laudus_import` pasa `_refresh_ledger_clone` como callback en vez de llamarlo antes
- `pipeline/importers/discrepancy_writer.py:19-21,87-95` — `_dedup_key(bank_account_id, year_month, line_no, je_id, state)`; `_key_of`/`_existing_dedup_keys` derivan los campos de la entrada (ya persisten ambos desde 6.5b)
- `pipeline/services/laudus_service.py:16-31,93-135` — `login()` propaga; `get_info_API`: `MAX_PAGES` (p.ej. 500) + raise si el page-param no avanza
- Tests: `backend/tests/test_laudus_run.py` (lock), `test_reconcile.py`/`test_reconcile_cartola.py` (dedup), `test_laudus_service.py` (paginación/login), `test_sync.py` (refresh dentro del lock)

## Tasks & Acceptance

**Execution:**
- [x] `pipeline/importers/laudus_run.py` — lock atómico + heartbeat + `refresh_clone` en run_import; tests: 2 threads → 1 gana; stale robado por UNO solo; heartbeat renueva mtime (max_age corto + sleep > max_age → el lock sobrevive); heartbeat muerto tras liberar
- [x] `backend/app/api/v1/sync/service.py` — refresh como callback; test: el orden observado es lock→refresh→fetch (monkeypatch registrando eventos)
- [x] `pipeline/importers/discrepancy_writer.py` — dedup key por contenido; tests: re-upload batch_id distinto → 0 nuevas; mismo batch idempotente; estados distintos de la misma línea NO colisionan (regresión 9.6b)
- [x] `pipeline/services/laudus_service.py` — MAX_PAGES + página-no-avanza → raise; `login()` propaga; tests: página repetida → raise; login con excepción → propaga la causa

**Acceptance Criteria:**
- Given dos writers compitiendo por el lock (incluido el caso stale), when ambos intentan adquirir, then exactamente uno lo hace y el otro espera o recibe LockTimeout
- Given un holder vivo cuya operación supera max_age, when un waiter evalúa el lock, then NO lo roba (mtime renovado por heartbeat)
- Given una cartola ya reconciliada, when se re-sube (batch_id nuevo) y se re-reconcilia, then el JSONL no gana ninguna discrepancia duplicada y los counts del dashboard no se inflan
- Given una API de Laudus que repite la misma página, when se fetchea, then la corrida termina failed en segundos (no loop infinito)
- Suite backend completa verde, 0 regresiones

## Verification

**Commands:**
- `python -m pytest backend/tests -q` — expected: verde, 0 regresiones

## Design Notes

Adjudicaciones del review de 3 capas (2026-07-06):

- **Ownership por token** (evolución post-review, convergencia Blind+Edge): heartbeat y release verifican que el lock siga siendo NUESTRO antes de tocarlo — un holder suspendido que revive ya no puede borrar el lock del ladrón legítimo ni renovarle el mtime a un lock ajeno. La devolución de un robo-en-falso va por `os.link` (falla si hay un tercero en el path — no clobber, a diferencia de `os.replace`).
- **El robo stale va por RENAME atómico + re-verificación** (el spec decía unlink+re-compete; el Auditor lo adjudicó como fortalecimiento compatible: el unlink literal tenía el hueco de borrar un lock fresco recién re-adquirido).
- **Residual documentado y logueado**: lock fantasma ≤300s con ≥3 contendientes + veredicto stale sobre fresco + μs (el Auditor lo calificó "estrictamente más angosto que el baseline", que doble-adquiría con 2 contendientes trivialmente). Perfección = byte-locks del OS; no hoy.
- **Discrepancia resuelta NO re-abre con la clave nueva**: comportamiento DESEADO del fix B4 — una discrepancia adjudicada por el contador no debe volver como ruido en cada re-upload; si la resolución anotó el ledger, el matcher deja de emitirla de todos modos. El sub-caso payload-stale quedó en deferred-work.
- **Guard de paginación**: `_extract_page` solo emite `{"page": N}` en sus 3 ramas (verificado), así que comparar `page` cubre todo hoy; se agregó str() a ambos lados por si la API alterna tipos.

**Resultado final (2026-07-06):** backend **694 passed / 1 xfailed** (0 regresiones; +10 tests, lock tests estables 20×+5×). Review 3 capas: Auditor PASS en las 11 filas de la matriz y AC1-AC4, boundaries limpias, robo-por-rename adjudicado como fortalecimiento; el CRITICAL del Blind Hunter (vacancia del robo) se cerró con ownership-token + give-back sin clobber; Edge Hunter verificó limpios los callers de login() (bootstrap ya lanzaba), los consumidores del batch_id (ninguno filtra discrepancias por él) y la liberación del lock en el path de excepción. 10 patches aplicados, 3 defer, resto dismiss.

## Suggested Review Order

**Lock (el corazón del batch)**

- Entry point: acquire_lock completo — O_EXCL + token + robo-por-rename + heartbeat verificado + GC de steal-files
  [`laudus_run.py:54`](../../pipeline/importers/laudus_run.py#L54)

- refresh_clone dentro del lock en run_import
  [`laudus_run.py:380`](../../pipeline/importers/laudus_run.py#L380)

- sync pasa el refresh como callback (con el warning de git clean)
  [`sync/service.py:117`](../../backend/app/api/v1/sync/service.py#L117)

**Dedup B4**

- Clave por identidad de contenido + residuales documentados
  [`discrepancy_writer.py:1`](../../pipeline/importers/discrepancy_writer.py#L1)

**Paginación B8**

- PaginationError + MAX_PAGES + no-avanza (str-compare) + login propaga con guard de token
  [`laudus_service.py:8`](../../pipeline/services/laudus_service.py#L8)

**Tests**

- Lock: contención, robo stale de a uno, heartbeat, ownership del release, GC, refresh-dentro-del-lock
  [`test_laudus_run.py:444`](../../backend/tests/test_laudus_run.py#L444)

- Dedup por contenido (re-upload no duplica, estados coexisten)
  [`test_reconcile.py:168`](../../backend/tests/test_reconcile.py#L168)

- Paginación + login
  [`test_laudus_service.py:116`](../../backend/tests/test_laudus_service.py#L116)
