# Story 7.0: Spike/decisión — ancla estable de comentarios + capa de persistencia (`owner_comments`)

Status: done  <!-- 2026-07-08 dev (agente) + review (mío): ancla 3 capas correcta, _tx_id_of idéntico al canónico de transactions/service.py, orphaned conservador, persistencia bajo lock sin bean-check. 17 tests, 729 passed/1 xfailed, 0 regresiones. Nits menores (copia de _tx_id_of; path git hardcodeado) no bloquean. -->

<!-- Story HABILITADORA del Epic 7 "Colaboración Owner-Contador". Bloquea 7.1–7.5.
     No entrega UI de usuario final; entrega la decisión de arquitectura + el módulo base
     (writer JSONL + estrategia de ancla resistente a re-imports) sobre el que se construye el resto. -->

## Story

As a **arquitecto del family office (habilitador para el owner y el contador)**,
I want **decidir y dejar implementada la estrategia de ancla de comentarios resistente a re-imports + la capa de persistencia append-only (`owner-comments.jsonl`) para hilos de comentario sobre transacciones**,
so that **los comentarios que el owner y el contador dejen sobre una transacción sigan apuntando a la transacción correcta después de que la cartola/Laudus se re-importe (cosa que hoy rompería un ancla ingenua por `tx_id`), y nunca se pierda un hilo aunque el ancla ya no resuelva**.

> **Por qué es una story aparte (habilitadora):** el resto del Epic 7 (7.1 crear comentario, 7.2 inbox+respuesta, 7.3 resolver, 7.4 chips) asume que existe (a) un `tx_id` de ancla que sobrevive a un re-import y (b) un lugar donde persistir los hilos. Ninguna de las dos existe hoy y ambas tienen una decisión de diseño no trivial (el `tx_id` actual **cambia** en cada re-import). Resolverlas una vez acá evita que cada story siguiente re-litigue lo mismo.

## El riesgo central que esta story resuelve (CRÍTICO)

El `tx_id` que el proyecto usa para identificar una transacción es:

```python
# backend/app/api/v1/transactions/service.py:31
def compute_tx_id(filename: str, lineno: int, narration: str, amount) -> str:
    base = f"{Path(filename).name}:{lineno}:{narration}:{amount}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]
```

El propio docstring lo advierte: es estable *"mientras beancount no re-numere líneas en un re-render determinista"*. Pero el Epic 6 demostró que **las cartolas se re-importan** (fix de categorización 2026-07-02, re-import feb+mar; idempotencia por slug que **sobrescribe el archivo entero**). Un re-import cambia `filename` (mismo slug, pero el archivo se re-genera) y sobre todo `lineno` (el orden/numeración de líneas cambia si cambia cualquier movimiento previo del mes). **Resultado: el `tx_id` de una transacción cambia → un comentario anclado solo por `tx_id` queda huérfano** apuntando a nada.

Este es el bug latente que esta story tiene que cerrar **antes** de que 7.1 empiece a escribir comentarios anclados.

### Estrategia de ancla decidida (default a implementar) — "ancla en 3 capas + snapshot, nunca perder el hilo"

Cada comentario/hilo guarda **tres coordenadas de ancla** + un **snapshot denormalizado** de la transacción:

| Campo persistido | Para qué | Volátil ante re-import |
|---|---|---|
| `tx_id` | lookup primario (rápido, O(1) por hash) | **SÍ** (cambia) |
| `ledger_git_sha` | procedencia/auditoría: contra qué estado del ledger se creó el comentario (permite explicar por qué el `tx_id` ya no resuelve) | n/a (es un hecho histórico) |
| `anchor_key` = clave semántica de respaldo = `sha( date · amount · account · narration_normalizada )` | **re-resolver el ancla** cuando el `tx_id` ya no matchea | **NO** (estable a través de re-imports: los datos contables no cambian, solo el filename/lineno) |
| `tx_snapshot` = `{date, amount, currency, account, narration}` capturado al crear el comentario | contexto humano si el ancla queda 100% huérfana (nunca mostrar un hilo "vacío") | n/a (congelado por diseño) |

**`narration_normalizada`** = `narration` en minúsculas, sin acentos (`unicodedata.NFKD` como `camel_leaf` en `beancount_promote.py:60`), colapsando espacios. **`account`** = `postings[0].account` (la misma pata que `compute_tx_id` usa para el `amount`, ver `_tx_id_of` en `transactions/service.py:40`).

**Algoritmo de resolución del ancla (en tiempo de lectura, ejecutado por 7.2/7.4):**

1. **Match directo por `tx_id`** contra los `entries` actuales del ledger. Si hay exactamente uno → ancla **RESUELTA** (estado `resolved`). Mostrar el hilo pegado a la transacción viva.
2. **Si no hay match por `tx_id`** → match por `anchor_key` (recomputada sobre los `entries` actuales). Si hay **exactamente uno** → ancla **RE-ANCLADA** (estado `re-anchored`); opcionalmente "sanar" reescribiendo el `tx_id` persistido al nuevo valor (append de una línea `anchor-heal`, no mutar). Mostrar el hilo pegado.
3. **Si hay cero o >1 matches** por `anchor_key` (transacción borrada, o ambigüedad) → ancla **HUÉRFANA** (estado `orphaned`). **Nunca se descarta el hilo**: se muestra en modo "histórico/degradado" usando el `tx_snapshot` congelado, con un aviso de que la transacción ancla ya no se encuentra en el ledger actual.

> **Principio no-negociable:** un comentario **nunca** se pierde ni se borra silenciosamente por un re-import. En el peor caso degrada a "histórico" mostrando el snapshot. Esto es lo que hace segura la decisión de anclar a nivel transacción sin bloquear los re-imports.

### Decisiones de alcance ya tomadas por Ary (no re-preguntar)

1. **Ancla a nivel TRANSACCIÓN, no line-item.** FR36 dice *"sobre una transacción o un ítem de línea"* — el **line-item se difiere**. Anclar a una pata específica agrega una cuarta coordenada volátil (el índice de posting) sin valor claro en el MVP (el owner comenta "esta transacción", no "esta pata"). Anotado como **mejora futura** en References. El ancla decidida (tx-level) ya guarda `postings[0].account` en el snapshot, así que subir a line-item después es aditivo, no un rework.
2. **Persistencia = `owner-comments.jsonl` append-only** en `ledger/_meta/`, commiteado+pusheado por git bajo `.import.lock`. **NO base de datos.** Mismo patrón que `discrepancy_writer.py` (append-only + `append_resolution`) y el flujo git de `beancount_promote.py`.
3. **Los comentarios NO son asientos contables.** No van a ningún archivo `.beancount`, no los lee el motor beancount, **no** pasan por `bean-check`. Son metadata de colaboración *sobre* el ledger, no parte de él. Esto preserva la integridad del ledger (un comentario mal formado jamás puede romper `bean-check` ni el reporte).

### Cambio de postura RBAC que esta story habilita (documentar, no implementar aún)

Hoy el rol **`family` (alias de `owner`) es solo-lectura**: **todos** los endpoints de escritura del backend usan `require_role(["contador","admin"])` (verificado: `transactions/router.py`, `reconciliation/router.py`, `cartolas`, `bank-accounts`). El Epic 7 es el **primer caso** donde `family` necesita endpoints de **escritura** (crear comentario en 7.1, responder en 7.2, resolver en 7.3, marcar leído en 7.4). Esta story **documenta y ratifica** la nueva postura, que las stories siguientes implementan:

> `family` puede escribir **comentarios** (y solo comentarios), nunca asientos del ledger. La superficie de escritura de `family` = `owner-comments.jsonl`, que por diseño no toca `.beancount` ni pasa por el motor. La garantía "el ledger es la fuente única y `family` no la puede mutar" **se mantiene intacta**.

El RBAC de los endpoints de comentarios será `require_role(["family","contador","admin"])` (los tres roles participan del hilo). Esta es la decisión; su implementación concreta ocurre en 7.1–7.4.

## Acceptance Criteria

1. **AC1 — Módulo writer `owner_comments` (append-only JSONL).** Existe `pipeline/importers/owner_comments_writer.py` (espejo de `discrepancy_writer.py`) con: `build_comment(...)` (arma el dict de un comentario raíz con `comment_id`, `thread_id`, ancla de 3 capas + `tx_snapshot`, `author_email`, `author_role`, `body`, `ts`), `append_comment(comment, path)` (append de una línea al JSONL, `mkdir` del `_meta/` si falta), `append_reply(thread_id, reply, path)` y `append_resolution(thread_id, resolution, path)` (líneas que referencian el `thread_id`, patrón `append_resolution` de `discrepancy_writer.py:128`), y `read_threads(path, thread_id=None)` que **pliega** las líneas por `thread_id` a hilos `{thread_id, root, replies[], resolution|None}`. Ruta por defecto `ledger/_meta/owner-comments.jsonl`. **Ningún** `.beancount` se toca, **ningún** `bean-check` corre.

2. **AC2 — Cómputo de la clave semántica de respaldo (`anchor_key`), pura y determinista.** Una función pura `compute_anchor_key(date, amount, account, narration) -> str` normaliza la narración (minúsculas, sin acentos, espacios colapsados) y devuelve un hash estable. Dado el mismo `(date, amount, account, narration)` con distinta capitalización/acentos/espaciado → **misma** `anchor_key`. Test: dos renders de la misma transacción (uno con `filename`/`lineno` distintos, simulando un re-import) → **distinto `tx_id`** pero **idéntica `anchor_key`**.

3. **AC3 — Resolvedor de ancla de 3 capas.** Una función pura `resolve_anchor(comment, entries) -> {status, tx_id, entry|None}` implementa el algoritmo: (1) match por `tx_id` → `status="resolved"`; (2) si falla, match por `anchor_key` recomputada sobre `entries`, exactamente uno → `status="re-anchored"` (+ el nuevo `tx_id`); (3) cero o >1 → `status="orphaned"`, `entry=None`. Tests para los tres caminos, incluido el caso re-import (el `tx_id` viejo no resuelve pero `anchor_key` sí → `re-anchored`) y el caso borrado (ni `tx_id` ni `anchor_key` → `orphaned`, el hilo sigue disponible con su `tx_snapshot`).

4. **AC4 — Captura del ancla al crear un comentario (helper reusable por 7.1).** Un helper `build_anchor(tx_id, entries, ledger_root) -> dict` localiza la transacción por `tx_id` (reusando la iteración de `_tx_id_of`, `transactions/service.py:40`), captura `tx_snapshot` (`date`, `amount`=`postings[0].units.number`, `currency`, `account`=`postings[0].account`, `narration`), computa `anchor_key` (AC2) y lee `ledger_git_sha` (ver AC5). Si el `tx_id` no resuelve contra los `entries` actuales → error claro (no se puede comentar sobre una tx inexistente). Devuelve el bloque de ancla que `build_comment` embebe.

5. **AC5 — Lectura del `ledger_git_sha`.** Un helper `ledger_head_sha(ledger_root) -> str | None` devuelve el SHA de `HEAD` del clon del ledger (`git -C <root> rev-parse HEAD`), tolerante a que git no esté disponible/inicializado (→ `None`, no crashea). Se persiste en cada comentario raíz como procedencia.

6. **AC6 — Persistencia git bajo lock (helper reusable por 7.1/7.2/7.3/7.4).** Un helper `persist_and_commit(mutate_jsonl, commit_msg, ledger_root)` envuelve la escritura al JSONL en el andamiaje de escritura del proyecto: `acquire_lock(.import.lock)` (`laudus_run.py:54`) → append a `owner-comments.jsonl` → `git_commit_push(root, ["ledger/_meta/owner-comments.jsonl"], msg)` (`laudus_run.py:208`, no-op si `IMPORTER_GIT_ENABLED` off). **Sin `bean-check`** (el JSONL no es parte del ledger cargable — diferencia deliberada con `apply_to_accounts` de `beancount_promote.py`, que sí lo corre porque escribe `accounts.beancount`). El helper es la única vía de escritura; las stories 7.1–7.4 lo consumen.

7. **AC7 — Documento de decisión (ADR breve) versionado.** Queda un archivo corto `_bmad-output/planning-artifacts/adr-owner-comments-ancla-persistencia.md` que registra: (a) el riesgo del `tx_id` volátil, (b) la estrategia de 3 capas + snapshot elegida, (c) por qué JSONL+git y no DB, (d) el cambio de postura RBAC de `family`, (e) qué se difirió (line-item, email). Es la referencia autoritativa que las stories 7.1–7.5 citan en vez de re-explicar.

8. **AC8 — Tests + sin regresiones.** Backend: `build_comment`/`append_*`/`read_threads` (round-trip: escribir raíz+2 respuestas+resolución → `read_threads` reconstruye el hilo con la resolución); `compute_anchor_key` (invariancia de normalización + estabilidad re-import); `resolve_anchor` (3 caminos); `build_anchor` (captura + tx inexistente → error); `ledger_head_sha` (sin git → `None`). Fixtures de ledger inline con `beancount.parser.parser.parse_string` (patrón `test_tc_cuadre.py`). `PYTHONUTF8=1 venv/Scripts/python.exe -m pytest backend/tests -q` → 0 regresiones nuevas.

## Tasks / Subtasks

- [ ] **Task 1 — Writer JSONL `owner_comments`** (AC1)
  - [ ] `pipeline/importers/owner_comments_writer.py` espejando `discrepancy_writer.py`: `SCHEMA_VERSION`, `build_comment(...)`, `append_comment`, `append_reply`, `append_resolution`, `read_threads`. Modelo de línea: cada evento es una línea (`type ∈ {comment, reply, resolution, anchor-heal}`) con `thread_id`; `read_threads` pliega por `thread_id`.
  - [ ] `comment_id`/`thread_id` = `uuid4` (el raíz define `thread_id = comment_id`). Sin dedup (append-only puro; los eventos son intencionalmente únicos, a diferencia de las discrepancias que sí dedupean por contenido).

- [ ] **Task 2 — Clave semántica + resolvedor de ancla** (AC2, AC3)
  - [ ] `compute_anchor_key(date, amount, account, narration)` — normalización NFKD + lower + colapso de espacios; hash sha256[:12].
  - [ ] `resolve_anchor(comment, entries)` — 3 capas; reusa `_tx_id_of`/`compute_tx_id` de `transactions/service.py` para el índice por `tx_id` y recomputa `anchor_key` sobre cada entry para la capa 2. Devuelve `{status, tx_id, entry}`.

- [ ] **Task 3 — Captura de ancla + git sha** (AC4, AC5)
  - [ ] `build_anchor(tx_id, entries, ledger_root)` — localiza la tx, arma `tx_snapshot`, computa `anchor_key`, adjunta `ledger_git_sha`.
  - [ ] `ledger_head_sha(ledger_root)` — `git rev-parse HEAD` tolerante a fallo.

- [ ] **Task 4 — Persistencia bajo lock** (AC6)
  - [ ] `persist_and_commit(mutate, commit_msg, ledger_root=None)` — `acquire_lock` → `mutate(path)` (el append) → `git_commit_push`. Sin `bean-check`. Default `ledger_root=_ledger_root()`.

- [ ] **Task 5 — ADR** (AC7)
  - [ ] `_bmad-output/planning-artifacts/adr-owner-comments-ancla-persistencia.md` con las 5 secciones de AC7.

- [ ] **Task 6 — Tests** (AC8)
  - [ ] `backend/tests/test_owner_comments_writer.py` (round-trip + read_threads), `test_owner_comments_anchor.py` (anchor_key + resolve_anchor 3 caminos + build_anchor). `monkeypatch.delenv("IMPORTER_GIT_ENABLED")` para el git no-op.

## Dev Notes

### Piezas existentes — REUSAR, no reinventar

| Pieza | Ubicación (verificada) | Uso en 7.0 |
|---|---|---|
| `compute_tx_id(filename, lineno, narration, amount)` | `backend/app/api/v1/transactions/service.py:31` | el `tx_id` primario (capa 1). **NO** cambiar su fórmula; solo consumirla. |
| `_tx_id_of(entry)` | `backend/app/api/v1/transactions/service.py:40` | mapear un `entry` → `tx_id` al indexar/recomputar. |
| `append_resolution` / `build_discrepancy` / dedup por `_key_of` | `pipeline/importers/discrepancy_writer.py:128` / :27 / :81 | **patrón** del writer append-only + resolución. El de comentarios NO dedupea (los eventos son únicos). |
| `acquire_lock(lock_path, ...)` | `pipeline/importers/laudus_run.py:54` | tomar `.import.lock` antes de escribir (serializa con el cron/importer). |
| `git_commit_push(repo_root, paths, message)` | `pipeline/importers/laudus_run.py:208` | commit+push del JSONL; no-op si `IMPORTER_GIT_ENABLED` off; propaga fallo real de git. |
| `_ledger_root()` | `pipeline/importers/laudus_run.py:38` | raíz del ledger (honra `LEDGER_DIR`). |
| `apply_to_accounts` (lock→mutate→bean-check→git) | `backend/app/services/beancount_promote.py:176` | **molde** del helper de escritura. **Diferencia clave:** 7.0 **omite** `bean_check` (el JSONL no es cargable por beancount). |
| `camel_leaf` (normalización NFKD ASCII) | `backend/app/services/beancount_promote.py:60` | referencia de cómo el proyecto normaliza texto para `anchor_key`. |

### Por qué JSONL + git y NO base de datos (registrar en el ADR)

- El proyecto **eliminó Supabase/Sheets** en el cutover c4 (9.16); Beancount + JSONL en `_meta/` es la única fuente. Meter una DB para comentarios re-abriría exactamente lo que se cerró.
- El backend en Render **clona el repo del ledger** al startup; una persistencia que no viva en el repo no sobrevive un redeploy. `owner-comments.jsonl` commiteado+pusheado sí sobrevive (igual que las discrepancias y los run-records).
- Append-only + git = audit trail e historia gratis (quién comentó/respondió/resolvió y cuándo), sin migraciones.

### Por qué el ancla NO puede ser solo `tx_id` (el corazón del spike)

Un re-import de cartola **sobrescribe el archivo completo con el mismo slug** (idempotencia por slug, Epic 6). Eso re-numera líneas → `lineno` cambia → `tx_id` cambia. Sin la capa `anchor_key`, cada re-import huerfanaría **todos** los comentarios de ese mes. La `anchor_key` se construye de datos **contables** (fecha, monto, cuenta, glosa) que el re-import preserva → sobrevive. El `ledger_git_sha` no participa de la resolución (los datos siguen siendo los mismos aunque el SHA avance); es procedencia/auditoría.

### Riesgo residual conocido (documentar, aceptar)

- **Colisión de `anchor_key`:** dos transacciones idénticas en fecha+monto+cuenta+glosa (ej. dos cargos iguales el mismo día) → la capa 2 devuelve >1 match → `orphaned` conservador (no re-ancla al azar). Aceptable: el hilo no se pierde (muestra snapshot); solo no se re-pega automáticamente. Mejora futura: desempatar por posición relativa dentro del mes.
- **Re-extracción con glosa distinta:** si una re-extracción de PDF cambia la narración, la `anchor_key` cambia → `orphaned`. Mismo residual que ya documenta `discrepancy_writer.py` ("líneas re-numeradas por una re-extracción distinta"). Aceptable para el MVP.

### Testing standards

- `pytest` en `backend/tests/`, `PYTHONUTF8=1` (gotcha Windows), venv `./venv/Scripts/python.exe`.
- Fixtures de ledger inline con `beancount.parser.parser.parse_string` (patrón de `test_tc_cuadre.py`).
- `monkeypatch.delenv("IMPORTER_GIT_ENABLED")` → `git_commit_push` no-op local.
- Los 2 rojos `test_fava_edit_validator` son PRE-EXISTENTES — no atribuírselos a esta story.

### Project Structure Notes

- Writer/lógica pura: `pipeline/importers/owner_comments_writer.py` (cohesión con `discrepancy_writer.py`).
- Persistencia bajo lock: puede vivir junto al writer o en `backend/app/services/owner_comments.py` (transporte-agnóstico, como `tc_cuadre.py`). El API (7.1+) irá en `backend/app/api/v1/owner_comments/`.
- Sin DB, sin Supabase, sin Sheets. `owner-comments.jsonl` en `ledger/_meta/` (junto a `cartola-discrepancies.jsonl` y `reconciliation-runs.jsonl`).

### References

- [Source: backend/app/api/v1/transactions/service.py:31] — `compute_tx_id` (el ancla volátil que este spike blinda).
- [Source: pipeline/importers/discrepancy_writer.py:128] — patrón writer append-only + `append_resolution` (molde del JSONL de hilos).
- [Source: backend/app/services/beancount_promote.py:176] — `apply_to_accounts` (molde de lock+git; 7.0 omite el bean-check).
- [Source: pipeline/importers/laudus_run.py:54,208,38] — `acquire_lock`, `git_commit_push`, `_ledger_root`.
- [Source: backend/app/dependencies.py:29,60] — roles `{family, contador, admin}`, `require_role`; `family` solo-lectura hoy → cambio de postura del Epic 7.
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 7] — Colaboración Owner-Contador, FR36–FR41.
- **Mejora futura (diferida):** ancla a nivel line-item (FR36 "o ítem de línea") — agrega el índice de posting como 4ta coordenada; el snapshot ya guarda `postings[0].account`, así que es aditivo.

## Decisiones de diseño para Ary (abiertas)

1. **¿"Sanar" el `tx_id` en el re-anchor (append `anchor-heal`) o solo re-resolver en caliente cada lectura?** Recomendado: **solo re-resolver en lectura** (más simple, sin escrituras extra); el `anchor-heal` es una optimización que se puede agregar si el volumen de comentarios crece. Default de esta story = re-resolver en lectura; el evento `anchor-heal` queda modelado en el schema pero no se emite aún.
2. **¿El `ledger_git_sha` se usa para algo más que auditoría?** Recomendado: **no en el MVP** (no gatea nada; solo se muestra en el detalle del hilo para trazabilidad). Si a futuro se quiere "este comentario es sobre una versión vieja del ledger", ya está el dato.
3. **Ubicación del helper de persistencia bajo lock** (`pipeline/importers/owner_comments_writer.py` vs `backend/app/services/owner_comments.py`). Sin impacto funcional; default = junto al writer para cohesión con el patrón de `discrepancy_writer`/`reconcile`.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (1M context) — dev-story 7.0.

### Completion Notes List

- **Módulo único `pipeline/importers/owner_comments_writer.py`** (opción por defecto del spike: writer +
  lógica pura + persistencia bajo lock juntos, cohesión con `discrepancy_writer.py`). Reusa
  `compute_tx_id` de `transactions/service.py` (import liviano: ese módulo solo trae hashlib/logging/
  datetime/pathlib/beancount, sin FastAPI → no hay ciclo ni peso extra) y `acquire_lock`/
  `git_commit_push`/`_ledger_root` de `laudus_run.py`.
- **Ancla de 3 capas (`resolve_anchor`, AC3):** (1) índice por `tx_id` (`_tx_id_of`) → exactamente uno =
  `resolved`; (2) fallback: recomputa `anchor_key` sobre cada `entry` vivo (`_anchor_key_of`) → exactamente
  uno = `re-anchored` con el **nuevo** `tx_id`; (3) cero o >1 = `orphaned`, `entry=None`. Devuelve
  `{status, tx_id, entry}`.
- **Degradado (`orphaned`):** `resolve_anchor` nunca lanza ni descarta; devuelve `entry=None` y el llamador
  (7.2/7.4) renderiza el hilo con el `tx_snapshot` congelado. Cubre tx borrada **y** `anchor_key` ambigua
  (dos tx idénticas → >1 match → orphaned conservador, no re-ancla al azar).
- **Decisión Ary aplicada:** re-resolución EN CALIENTE, sin "sanar" el JSONL. El evento `anchor-heal` está
  modelado en el schema (`read_threads` lo ignora explícitamente) pero **no se emite** en 7.0.
- **`compute_anchor_key` (AC2):** `sha256(date · amount · account · narration_normalizada)[:12]`.
  Normalización NFKD→ASCII + lower + colapso de espacios (misma técnica que `camel_leaf`). Acepta
  `date`/Decimal/str. Test de invariante: dos renders con distinto filename/lineno → **distinto `tx_id`,
  idéntica `anchor_key`**.
- **`persist_and_commit` (AC6):** `acquire_lock(.import.lock)` → `mutate(path)` (el append) →
  `git_commit_push(["ledger/_meta/owner-comments.jsonl"])`. **Sin `bean-check`** (el JSONL no es cargable
  por beancount — diferencia deliberada con `apply_to_accounts`). Es la única vía de escritura para 7.1–7.4.
- **`read_threads` pliega por `thread_id`** a `{thread_id, root, replies[], resolution|None}`; la última
  línea `resolution` gana (patrón "último run gana" de `list_periods`).
- **ADR:** `_bmad-output/planning-artifacts/adr-owner-comments-ancla-persistencia.md` con las 5 secciones
  de AC7 (riesgo `tx_id` volátil, estrategia 3 capas + snapshot, JSONL+git vs DB, postura RBAC de `family`,
  diferidos).
- **Tests:** 17 nuevos (8 writer/persistencia, 9 anchor). Suite completa `PYTHONUTF8=1 pytest backend/tests -q`
  → **729 passed, 1 xfailed** (baseline 712 + 17 nuevos, **0 regresiones**). Nota: los 2 rojos históricos de
  `test_fava_edit_validator` no aparecen en esta corrida (0 failed).
- **Sin git commit/push** (pendiente de review, como pidió el brief). Working tree tiene: el módulo nuevo,
  los 2 archivos de test y el ADR.
- **Desvío menor:** `_normalize_narration` se hizo helper privado en vez de inline dentro de
  `compute_anchor_key` (legibilidad; sin impacto funcional).

### File List

- `pipeline/importers/owner_comments_writer.py` (nuevo) — writer JSONL + ancla 3 capas + `persist_and_commit`.
- `backend/tests/test_owner_comments_writer.py` (nuevo) — `build_comment`/`append_*`/`read_threads` round-trip + `persist_and_commit` (con y sin git).
- `backend/tests/test_owner_comments_anchor.py` (nuevo) — `compute_anchor_key` (AC2) + `resolve_anchor` 3 caminos (AC3) + `build_anchor`/`ledger_head_sha` (AC4/AC5).
- `_bmad-output/planning-artifacts/adr-owner-comments-ancla-persistencia.md` (nuevo) — ADR (AC7).

### Change Log

- 2026-07-08 — Story 7.0 implementada (spike/enabler Epic 7). Módulo `owner_comments_writer`, ancla de 3
  capas resistente a re-imports, persistencia append-only bajo lock, ADR. 17 tests nuevos, suite 729
  passed/1 xfailed sin regresiones. Status → review. Sin commit (a pedido).
