# ADR — Ancla de comentarios resistente a re-imports + persistencia `owner-comments.jsonl`

Estado: **Aceptado** (Story 7.0, habilitadora del Epic 7 "Colaboración Owner-Contador").
Fecha: 2026-07-08. Es la referencia autoritativa que citan 7.1–7.5 (no re-explicar acá lo decidido).

## Contexto

El Epic 7 deja al owner (`family`) y al contador comentar sobre transacciones del ledger. Eso exige
(a) un ancla que identifique la transacción de forma estable y (b) un lugar donde persistir los hilos.
Ninguna de las dos existía y ambas tienen una decisión de diseño no trivial.

## (a) El riesgo: el `tx_id` es volátil ante un re-import

El identificador de transacción del proyecto es
`compute_tx_id = sha256(filename, lineno, narration, amount)[:12]`
(`backend/app/api/v1/transactions/service.py:31`). Su propio docstring lo advierte: estable *"mientras
beancount no re-numere líneas en un re-render determinista"*.

Pero el Epic 6 demostró que **las cartolas se re-importan** (fix de categorización 2026-07-02, re-import
feb+mar). La idempotencia por slug **sobrescribe el archivo completo del mes**; si cambió cualquier
movimiento previo, se re-numeran las líneas → `lineno` cambia (y `filename` puede cambiar por el slug
re-generado) → **el `tx_id` de una transacción cambia**. Un comentario anclado SOLO por `tx_id` quedaría
huérfano apuntando a nada tras cada re-import. Cerrar este bug latente **antes** de que 7.1 empiece a
escribir comentarios es el objeto de este spike.

## (b) Decisión — ancla de 3 capas + snapshot, re-resuelta en caliente

Cada comentario raíz guarda tres coordenadas de ancla + un snapshot congelado:

| Campo | Para qué | ¿Volátil ante re-import? |
|---|---|---|
| `tx_id` | lookup primario O(1) | **SÍ** |
| `ledger_git_sha` | procedencia/auditoría (contra qué estado del ledger se creó) | n/a (hecho histórico) |
| `anchor_key = sha(date · amount · account · narration_normalizada)[:12]` | re-anclar cuando el `tx_id` ya no matchea | **NO** (datos contables, el re-import los preserva) |
| `tx_snapshot = {date, amount, currency, account, narration}` | contexto humano si el ancla queda huérfana | n/a (congelado por diseño) |

`narration_normalizada` = NFKD→ASCII (misma técnica que `camel_leaf`, `beancount_promote.py:60`) +
minúsculas + espacios colapsados. `account` = `postings[0].account` (la misma pata que `compute_tx_id`
usa para el `amount`).

**Resolución en tiempo de lectura (`resolve_anchor`), 3 capas:**

1. Match por `tx_id` contra los `entries` vivos → exactamente uno → `resolved`.
2. Si falla → match por `anchor_key` recomputada sobre los `entries` → exactamente uno → `re-anchored`
   (con el nuevo `tx_id`).
3. Cero o >1 matches → `orphaned`: el hilo se muestra en modo histórico/degradado con su `tx_snapshot`.

**Principio no-negociable:** un comentario **nunca** se pierde ni se borra silenciosamente por un
re-import. En el peor caso degrada a "histórico". Esto es lo que hace segura la decisión de anclar a
nivel transacción sin bloquear los re-imports.

**Re-resolución EN CALIENTE, no "sanar" el JSONL** (decisión Ary, 7.0): ante un `tx_id` que ya no matchea,
la capa 2 re-ancla en cada lectura; **NO** se reescribe el `tx_id` persistido. El evento `anchor-heal`
queda modelado en el schema pero no se emite en esta story (es una optimización futura si el volumen de
comentarios crece). Más simple, sin escrituras extra, y el `tx_snapshot` garantiza que el hilo nunca
quede vacío.

`ledger_git_sha` **no** participa de la resolución (los datos siguen siendo los mismos aunque el SHA
avance); es solo procedencia/auditoría.

## (c) Por qué JSONL + git y NO base de datos

- El proyecto **eliminó Supabase/Sheets** en el cutover c4 (Story 9.16); Beancount + JSONL en `_meta/`
  es la única fuente. Meter una DB para comentarios re-abriría exactamente lo que se cerró.
- El backend en Render **clona el repo del ledger** al startup; una persistencia que no viva en el repo
  no sobrevive un redeploy. `owner-comments.jsonl` commiteado+pusheado sí sobrevive (igual que las
  discrepancias y los run-records).
- Append-only + git = audit trail e historia gratis (quién comentó/respondió/resolvió y cuándo), sin
  migraciones.

**Los comentarios NO son asientos contables.** No van a ningún `.beancount`, no los lee el motor
beancount y **no** pasan por `bean-check` (diferencia deliberada con `apply_to_accounts`, que sí lo corre
porque escribe `accounts.beancount`). Un comentario mal formado jamás puede romper `bean-check` ni el
reporte. Persistencia = `ledger/_meta/owner-comments.jsonl` append-only, escrito bajo `.import.lock` y
commiteado+pusheado por `git_commit_push` (patrón `discrepancy_writer.py` + `laudus_run.py`).

## (d) Cambio de postura RBAC de `family` (que este ADR ratifica)

Hoy el rol **`family` (alias de `owner`) es solo-lectura**: todos los endpoints de escritura del backend
usan `require_role(["contador","admin"])`. El Epic 7 es el **primer caso** donde `family` necesita
endpoints de **escritura** (crear comentario, responder, resolver, marcar leído).

> `family` puede escribir **comentarios** (y solo comentarios), nunca asientos del ledger. Su superficie
> de escritura = `owner-comments.jsonl`, que por diseño no toca `.beancount` ni pasa por el motor. La
> garantía "el ledger es la fuente única y `family` no la puede mutar" **se mantiene intacta.**

El RBAC de los endpoints de comentarios será `require_role(["family","contador","admin"])`. Esta es la
decisión; su implementación concreta ocurre en 7.1–7.4.

## (e) Diferido / fuera de alcance

- **Ancla a nivel line-item** (FR36 "o ítem de línea"): se difiere. Anclar a una pata agrega el índice
  de posting como 4ta coordenada volátil sin valor claro en el MVP (el owner comenta "esta transacción",
  no "esta pata"). El snapshot ya guarda `postings[0].account`, así que subir a line-item después es
  **aditivo**, no un rework.
- **`anchor-heal`** (reescribir el `tx_id` sanado): modelado, no emitido (ver punto b).
- **`ledger_git_sha` como gate**: hoy solo se muestra para trazabilidad; no gatea nada.
- **Notificaciones por email**: fuera de 7.0.

## Riesgo residual conocido (aceptado)

- **Colisión de `anchor_key`:** dos transacciones idénticas en date+amount+account+narration (ej. dos
  cargos iguales el mismo día) → la capa 2 devuelve >1 match → `orphaned` conservador (no re-ancla al
  azar). Aceptable: el hilo no se pierde (muestra snapshot); solo no se re-pega automáticamente. Mejora
  futura: desempatar por posición relativa dentro del mes.
- **Re-extracción con glosa distinta:** si una re-extracción de PDF cambia la narración, la `anchor_key`
  cambia → `orphaned`. Mismo residual que ya documenta `discrepancy_writer.py`. Aceptable para el MVP.

## Implementación

`pipeline/importers/owner_comments_writer.py` (espeja `discrepancy_writer.py`):
`compute_anchor_key`, `resolve_anchor`, `build_anchor`, `ledger_head_sha`, `build_comment`,
`append_comment`/`append_reply`/`append_resolution`, `read_threads`, `persist_and_commit` (lock→append→git,
sin bean-check). Tests: `backend/tests/test_owner_comments_writer.py`, `test_owner_comments_anchor.py`.
