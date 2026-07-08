# Story 7.3: Resolver un hilo de comentario (ambos roles) — FR40

Status: draft

<!-- Depende de 7.0 (writer + append_resolution de hilos) y 7.2 (inbox donde se resuelve). -->

## Story

As a **owner o contador del family office**,
I want **marcar un hilo de comentario como resuelto cuando la duda ya quedó aclarada**,
so that **el hilo salga del inbox de pendientes y no siga apareciendo como algo que requiere atención — dejando el registro de que se cerró, quién y cuándo**.

## Contexto

7.1/7.2 dejaron los hilos creándose y respondiéndose, pero **siempre abiertos**: el inbox `?status=open` los muestra para siempre. Esta story cierra el ciclo (**FR40**): cualquiera de los dos participantes puede **resolver** un hilo. Es el análogo directo de `append_resolution` en la reconciliación (`discrepancy_writer.py:128`), aplicado a hilos de comentario: una línea de resolución append-only que referencia el `thread_id`, y el hilo pasa a `resolved` (deja de aparecer en `?status=open`).

## Acceptance Criteria

1. **AC1 — Resolver un hilo abierto (FR40).**
   Given un hilo abierto,
   When un `family`/`contador`/`admin` llama `POST /api/v1/comments/{thread_id}/resolve` (opcional `{note}`),
   Then se appendea una línea de resolución (`append_resolution`, 7.0 AC1) con `resolved_by` (email), `resolved_by_role`, `resolved_at` (timestamp) y `note` opcional; se commitea+pushea (`persist_and_commit`); y el hilo deja de aparecer en `GET /comments?status=open`. Devuelve `{thread_id, resolved_at}` (200).

2. **AC2 — Ambos roles pueden resolver (FR40).**
   Given el endpoint,
   Then usa `require_role(["family","contador","admin"])`. Tanto el owner (que abrió el hilo) como el contador (que respondió) pueden cerrarlo — no está restringido al autor. Test explícito: un `family` resuelve un hilo → 200.

3. **AC3 — Idempotencia: no resolver dos veces.**
   Given un hilo ya resuelto (ya tiene línea de resolución),
   When se llama `resolve` de nuevo,
   Then se rechaza con un error claro (patrón de `resolve()` en reconciliación: `"hilo ya resuelto"` → 409/400), **antes** de escribir nada. No se appendea una segunda resolución.

4. **AC4 — Resolver un `thread_id` inexistente.**
   Given un `thread_id` que no existe → 404, sin escritura.

5. **AC5 — El estado `resolved` se refleja en el inbox.**
   Given un hilo resuelto,
   Then `GET /comments?status=open` **no** lo lista; `?status=resolved` sí; `?status=all` lo lista con su bloque `resolution`. (Verifica que 7.2 y 7.3 comparten la misma definición de "abierto" = sin línea de resolución.)

6. **AC6 — Acción de resolver en la UI.**
   Given el inbox (7.2),
   When el usuario toca "Marcar resuelto" en un hilo,
   Then llama `resolve`, el hilo se marca visualmente como resuelto y sale de la vista de abiertos. Botón visible para ambos roles. Sin toasts.

7. **AC7 — Tests + sin regresiones.**
   Backend: resolver abierto → línea de resolución + sale de `?status=open` (AC1, AC5); `family` resuelve → 200 (AC2); doble resolución → rechazada sin segunda escritura (AC3); `thread_id` inexistente → 404 (AC4). Frontend: component test del botón resolver (el hilo desaparece de abiertos). Suites verdes, 0 regresiones nuevas.

## Tasks / Subtasks

- [ ] **Task 1 — Endpoint de resolución** (AC1, AC2, AC3, AC4)
  - [ ] `POST /comments/{thread_id}/resolve` en `owner_comments/router.py` (RBAC family/contador/admin). Service `resolve_thread(thread_id, note, user_email, user_role, ledger_root)`: (1) `read_threads(thread_id=...)` → 404 si no existe; (2) guard "ya resuelto" (si `resolution is not None`) → error → 409/400 **antes** de escribir; (3) `append_resolution(thread_id, {...}, path)` → `persist_and_commit`.
  - [ ] Schema `ResolveThreadRequest{note: str | None = None}` / `ResolveThreadResponse{thread_id, resolved_at}`. Excepción `ThreadResolveError` → 409/400 (patrón `ResolveError`→400 de reconciliación).

- [ ] **Task 2 — Acción de resolver en el inbox** (AC6)
  - [ ] `ownerComments.ts`: `resolveThread(thread_id, note?)`.
  - [ ] Botón "Marcar resuelto" en `CommentsInboxPage` (7.2), visible para ambos roles. Al éxito, refetch o quita el hilo de la lista de abiertos.

- [ ] **Task 3 — Tests** (AC7)
  - [ ] `backend/tests/test_owner_comments_resolve.py`: resolver abierto + sale de open; `family` 200; doble resolución rechazada; 404. Frontend component test.

## Dev Notes

### Piezas consumidas

| Pieza | De dónde | Uso |
|---|---|---|
| `append_resolution(thread_id, resolution, path)` | `owner_comments_writer` (7.0 AC1) | la línea de cierre (espejo de `discrepancy_writer.py:128`) |
| `read_threads(path, thread_id=...)` | 7.0 AC1 | localizar el hilo + leer su `resolution` para el guard de idempotencia |
| `persist_and_commit` | 7.0 AC6 | lock → append → git |
| inbox `GET /comments?status` | 7.2 AC1 | la definición compartida de "abierto" (sin `resolution`) |

### Patrón de idempotencia (heredado, verificado)

El `resolve()` de reconciliación (`reconciliation/service.py`) ya hace exactamente esto: guard "ya resuelta" **antes** de cualquier escritura, y el router mapea `ResolveError` → 400 (`reconciliation/router.py:81`). Esta story replica el patrón para hilos: el guard corre antes del `append_resolution`, así nunca hay dos resoluciones para el mismo hilo. **No reinventar** el manejo de error; espejar el de reconciliación.

### Definición única de "resuelto"

"Abierto" vs "resuelto" se deriva de **una sola cosa**: si el hilo tiene una línea de resolución (`resolution is not None` tras `read_threads`). 7.2 (inbox) y 7.3 (resolver) **deben** compartir esa definición — no introducir un flag paralelo. Esto mantiene el JSONL como fuente única del estado del hilo.

### Anti-alcance

- **No** hay "reabrir" en el MVP (una vez resuelto, queda resuelto; una respuesta post-resolución no reabre — ver decisión de 7.2). Reabrir = mejora futura (append de una línea `reopen`).
- **No** notifica (7.4).

### Testing standards

- `pytest` `backend/tests/`, `PYTHONUTF8=1`, venv local, `monkeypatch.delenv("IMPORTER_GIT_ENABLED")`. Frontend `vitest` + `tsc`.

### References

- [Source: _bmad-output/implementation-artifacts/7-0-spike-ancla-persistencia-comentarios.md] — `append_resolution`, `read_threads`, `persist_and_commit`.
- [Source: _bmad-output/implementation-artifacts/7-2-inbox-contador-respuesta.md] — inbox + definición de "abierto".
- [Source: pipeline/importers/discrepancy_writer.py:128] — `append_resolution` (molde).
- [Source: backend/app/api/v1/reconciliation/service.py] — `resolve()` + guard de idempotencia (molde).
- [Source: backend/app/api/v1/reconciliation/router.py:81] — mapeo `ResolveError`→400.
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 7] — FR40.

## Decisiones de diseño para Ary (abiertas)

1. **¿Resolver requiere una nota obligatoria?** Recomendado: **nota opcional** (cerrar rápido sin fricción; el hilo ya tiene el historial). Default = opcional.
2. **¿Código HTTP para doble-resolución?** Reconciliación usa 400 (`ResolveError`). ¿Mantener 400 por consistencia, o 409 (más semántico para "conflicto de estado")? Default = **400** por consistencia con reconciliación; cambiar a 409 es trivial si Ary prefiere.
3. **¿Reabrir en el MVP?** Recomendado: **no** (diferido). Confirmar que "resuelto es final" es aceptable para el owner.

## Dev Agent Record

### Agent Model Used

_(pendiente)_

### Completion Notes List

_(pendiente)_

### File List

_(pendiente)_
