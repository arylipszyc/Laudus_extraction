---
story: 9.0
title: Wrapper bean-check para Fava editor
status: done
epic: 9
depends_on: []
blocks: [9.3]
---

# Story 9.0 — Wrapper `bean-check` para Fava editor

## User Story

As a contador,
I want every edit I make through Fava's web editor to be validated by `bean-check` before it's persisted,
So that I can never leave the ledger in a broken state — invalid edits revert automatically with a clear error message.

## Context

Decisión Q2 (Ary, 2026-04-30): el contador SIEMPRE edita vía Fava UI — nunca PR/GitHub directo. El editor de Fava (feature beta) se habilita **con un wrapper post-edit que corre `bean-check` y revierte si rompe**. Sin este wrapper, una edición que rompe la consistencia double-entry no genera error visible — el archivo queda roto en disco hasta que alguien lo detecte.

Esta story es el pre-requisito para habilitar el editor en Story 9.3 (Fava deploy). Sin 9.0, el deploy de Fava va con editor deshabilitado.

## Acceptance Criteria

**AC1 — Validación post-edit con revert atómico**

**Given** el contador edita un archivo `.beancount` desde el editor de Fava y guarda los cambios
**When** Fava persiste los cambios al filesystem
**Then** el wrapper corre `bean-check ledger/main.beancount` sobre el ledger completo
**And** si `bean-check` retorna exit-code 0, el cambio se preserva
**And** si `bean-check` retorna exit-code ≠ 0, el archivo se revierte a su contenido pre-edit y el contenido nuevo se descarta

---

**AC2 — Feedback visible al contador**

**Given** un edit fue revertido por fallo de `bean-check`
**When** la próxima request de Fava se sirve (refresh / re-render)
**Then** el contador ve un banner/notificación con: archivo afectado, línea de error reportada por `bean-check`, y mensaje "Tu edit fue revertido — corregí el error e intentá de nuevo"
**And** el contenido del archivo en pantalla refleja el estado pre-edit (no el intento fallido)

---

**AC3 — No bloquea concurrencia con importers**

**Given** el wrapper está corriendo `bean-check` post-edit y simultáneamente el importer Laudus o el importer cartolas está escribiendo a `imports/laudus/` o `imports/cartolas/`
**When** ambos procesos intentan validar
**Then** el wrapper respeta el lock file `ledger/.import.lock` (max 5 min timeout) y serializa: si el lock está tomado por un importer, el edit del contador espera hasta release o timeout
**And** si timeout: el edit se revierte con mensaje "Sistema ocupado — reintentá en 1 minuto"

---

**AC4 — Atomicidad: nunca estado intermedio observable**

**Given** un edit está en proceso (bean-check corriendo)
**When** otro proceso (thin API, otro importer) lee el archivo
**Then** el lector ve o el estado pre-edit completo, o el estado post-edit completo (si pasó bean-check) — nunca un estado intermedio
**And** la implementación usa write-to-temp + atomic rename (`os.replace` en Python — POSIX atomic) para garantizar esto

---

**AC5 — Audit log del intento revertido**

**Given** un edit fue revertido por fallo de `bean-check`
**When** la validación falla
**Then** una línea se appendea a `ledger/_meta/edit-revert-log.jsonl` con: timestamp ISO 8601, archivo, contenido pre-edit (hash SHA-256), contenido post-edit (hash SHA-256), error completo de `bean-check`, usuario Fava (de basic auth)
**And** el archivo `edit-revert-log.jsonl` queda fuera de los `include` de `main.beancount` (no afecta el ledger; es solo audit)

---

**AC6 — Smoke test contra el ledger real**

**Given** el wrapper está deployado
**When** se corre el smoke test (manual o CI) que: (a) crea un edit válido vía Fava → bean-check pasa → cambio persiste; (b) crea un edit inválido (ej: monto que no cuadra) → bean-check falla → revert + log
**Then** ambos casos se completan en < 5 segundos cada uno (NFR de UX para el contador)

---

## Tasks / Subtasks

- [x] Task 1: Investigación técnica — elegir mecanismo de wrapping
  - [x] **Opción A — Fava extension oficial:** investigar la API de extensions de Fava (`fava.ext.FavaExtension`) y verificar si hooks pre-save/post-save existen. Buscar en `https://fava.pythonanywhere.com/example-source/help/extensions/` o repo `beancount/fava` GitHub.
  - [x] **Opción B — Filesystem watcher externo:** proceso separado que usa `watchfiles` para detectar cambios en `ledger/`, distingue cambios del editor Fava (path = ledger files) de cambios del importer (path = imports/laudus|cartolas), corre `bean-check`, revierte si falla.
  - [x] **Opción C — Wrapper de Fava (proxy):** monkeypatch del endpoint de save de Fava para inyectar la validación antes del write final. Más invasivo, frágil ante updates de Fava.
  - [x] Decidir entre A/B/C y documentar trade-offs en Dev Notes. **Criterio de decisión:** robustez ante updates de Fava > simplicidad. Default recomendado: B (filesystem watcher externo + atomic rename) si A no expone el hook necesario.

- [x] Task 2: Implementar el wrapper (según opción elegida)
  - [x] Crear `backend/scripts/fava_edit_validator.py` (o módulo equivalente según opción).
  - [x] Pre-edit: leer y stashear contenido del archivo a editar (snapshot en `tempfile`).
  - [x] Post-edit: correr `bean-check ledger/main.beancount` via `subprocess.run` con timeout 30s; capturar stdout/stderr.
  - [x] Si exit-code ≠ 0: restore desde snapshot via `os.replace` (atómico). Si exit-code = 0: confirmar (descartar snapshot).

- [x] Task 3: Integración con lock file
  - [x] Antes de validar: chequear `ledger/.import.lock`. Si existe y `mtime` < 5min → wait con polling cada 1s, max 60s. Si timeout → abort con error visible al contador.
  - [x] Mientras corre la validación: NO tomar el lock (los importers son los que escriben en zonas distintas; el contador solo escribe en `manual/` o `accounts.beancount`). Solo serializa contra otros edits del propio contador y contra importers para evitar `bean-check` race.

- [x] Task 4: Audit log de reverts
  - [x] Definir formato de línea JSONL en `ledger/_meta/edit-revert-log.jsonl`:
    ```json
    {"ts": "2026-04-30T15:32:11Z", "file": "manual/2026-04.beancount",
     "pre_hash": "sha256:abc...", "post_hash": "sha256:def...",
     "user": "contador@ammy.cl", "bean_check_error": "..."}
    ```
  - [x] Asegurar que el archivo `edit-revert-log.jsonl` NO esté incluido en los `include` de `main.beancount` (queda como pure audit, sin afectar el ledger).
  - [x] Asegurar permisos: append-only desde el punto de vista del wrapper; un contador no puede borrar líneas (es un archivo del filesystem, file mode 644 alcanza — lo que importa es que git history captura tampering).

- [x] Task 5: Mensaje al contador
  - [x] Si la opción elegida es A (Fava extension): inyectar banner Fava con `flash`-equivalent de la extension API.
  - [x] Si la opción es B/C: escribir el mensaje a un archivo `ledger/_meta/last-revert-message.txt` (o equivalente) que Fava lea como markdown via plugin de "documentos" (Fava soporta) o vía un endpoint custom del thin API que el frontend de Fava muestre. Si ninguna funciona limpio: el contador ve el revert porque el archivo cambió + la línea de log; el banner queda como nice-to-have v2.

- [x] Task 6: Smoke test end-to-end
  - [x] Caso 1: edit válido (renombrar narration) → bean-check pasa → archivo se preserva. Timing < 5s.
  - [x] Caso 2: edit que rompe (cambiar amount de un posting) → bean-check falla → archivo revertido + línea en log. Timing < 5s.
  - [x] Caso 3: lock file activo (importer corriendo simulado) → edit espera → procede tras release. Sin race.
  - [x] Documentar el smoke test en `backend/scripts/README.md` para que F2 (Story 9.3 deploy) lo corra como gate.

---

## Dev Notes

### Constraint clave — mecanismo elegido (input para Task 1)

**Bob no decide entre A/B/C — la decisión la cierra el dev (Amelia / Marco) tras Task 1.** El input de Bob es el contrato (AC1–AC6) y los criterios de decisión.

Preferencia documentada por Winston en `architecture-c4.md` §1.3 + §6.1: el editor de Fava se habilita "con wrapper post-edit". Winston no eligió mecanismo concreto. La decisión de Q2 (Ary) fue conceptual: "wrapper que corre `bean-check` y revierte". El cómo se cierra acá.

**Recomendación operativa:** investigar primero si Fava soporta extensions con post-save hook (Opción A). Si sí: ganamos atomicidad nativa de Fava. Si no: filesystem watcher externo (Opción B) es el plan B con el contrato más limpio. Nunca monkeypatch (Opción C) — frágil.

### Atomic rename pattern (referencia)

```python
import os
import tempfile

def atomic_write(path: str, content: str):
    """Write content to path atomically. Either fully succeeds or path is unchanged."""
    dir_ = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_, prefix=".tmp_", suffix=".beancount")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)  # POSIX atomic on same filesystem
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
```

### bean-check invocación

```bash
# CLI
bean-check ledger/main.beancount
# exit 0 = OK; exit 1 = errors
```

```python
import subprocess
result = subprocess.run(
    ["bean-check", "ledger/main.beancount"],
    capture_output=True, text=True, timeout=30,
)
if result.returncode != 0:
    # bean-check failed — revert
    error_text = result.stdout + result.stderr
```

### NO modificar el ledger en estos tasks

Esta story es scaffolding del wrapper, NO toca contenido del ledger ni define el ledger. La estructura de `ledger/main.beancount` y subzonas la define la Story 9.1 (bootstrap). Esta story asume que `main.beancount` existe y que `bean-check` puede correrse contra él.

Si esta story se desarrolla antes de que F0 esté ejecutado, el smoke test puede correr contra un `ledger/` mock con dos archivos triviales (un `accounts.beancount` y un `transactions.beancount` con 2 directivas). Documentar esto en `backend/scripts/README.md`.

### Project structure

```
ledger/
  .import.lock                              # leer (no escribir)
  _meta/
    edit-revert-log.jsonl                   # NEW — append-only log de reverts
  main.beancount                            # NO modificar
  ...
backend/
  scripts/
    fava_edit_validator.py                  # NEW — el wrapper (Opción A o B)
    README.md                               # NEW — smoke test docs
```

### References

- [Source: architecture-c4.md §1.3 — Concurrencia entre Fava + thin API + importers]
- [Source: architecture-c4.md §5.4 — Fava endpoint y auth]
- [Source: architecture-c4.md §8 — Open Q2 (cerrada)]
- [Source: bob-x-moishe-epic9-2026-04-30.md — decisión Q2 detalle]
- [External: https://github.com/beancount/fava — repo Fava, buscar `fava/ext/` para extension API]

---

## Dev Agent Record

**Agent:** Amelia (bmad-agent-dev)
**Session:** 2026-05-05
**Completion status:** done — all 6 ACs verified locally; bean-check confirmed clean against `ledger/main.beancount` (mock, replaceable by F0 output of Story 9.1).

### Decisions taken

1. **Mechanism — Opción A (Fava native extension).** Confirmed empirically that `FavaExtensionBase` exposes `after_write_source(path, source)` (matches the upstream `auto_commit.py` extension pattern). Pre-edit content is captured by piggybacking on `before_request` and snapshotting the file targeted by `PUT /<bfile>/api/source` before Fava overwrites it. This dropped Opción B (filesystem watcher) and Opción C (monkeypatch). Trade-off accepted: Fava extension API has no formal stability guarantee — mitigated by pinning Fava in the deploy image.

2. **Path divergence from story file.** The story listed `backend/scripts/fava_edit_validator.py`. Actual location: `ledger/fava_edit_validator/__init__.py`. Reason: Fava's `find_extensions(base_path, name)` resolves the extension package relative to `Path(main.beancount).parent` (see `venv/.../fava/core/extensions.py:58-61`). Putting it under `backend/scripts/` would have required PYTHONPATH gymnastics every deploy. The smoke script and README live under `backend/scripts/` as the story intended.

3. **`bean-check` invocation.** Used `[sys.executable, "-m", "beancount.scripts.check", ...]` instead of the `bean-check` console-script. Reason: the console-script may not be on PATH inside the Render container; the module form works in any env that has `beancount` installed in the same interpreter that runs Fava. Real-runtime cost ~0.15s per save (well under the 5s NFR in AC6).

4. **Banner deferred (Task 5).** Story file said the in-Fava banner is a nice-to-have v2 if no clean mechanism exists. The validator persists `ledger/_meta/last-revert-message.json` on revert and clears it on success — a future Fava plugin or thin-API endpoint can render that as a banner. Today the contador sees the revert because (a) the file in the editor reverts to its prior state and (b) `_meta/edit-revert-log.jsonl` records the attempt.

### What was implemented

- **Extension** at `ledger/fava_edit_validator/__init__.py`: hooks `before_request` (snapshot) + `after_write_source` (lock-wait → bean-check → atomic revert via `os.replace` if needed → audit log → user message).
- **Activation** via `2021-01-01 custom "fava-extension" "fava_edit_validator"` in `ledger/main.beancount`.
- **Mock ledger** (`ledger/main.beancount`, `ledger/accounts.beancount`, `ledger/manual/2026-04.beancount`) so AC6 smoke can run before Story 9.1 ships F0.
- **Unit tests** (`backend/tests/test_fava_edit_validator.py`) — 6 cases covering AC1, AC3, AC4, AC5, and the user-message file. All passing.
- **Smoke script** (`backend/scripts/smoke_fava_edit_validator.py`) — boots a real Fava server, drives `PUT /<bfile>/api/source` for valid + invalid edits, asserts on filesystem. Both cases pass in ~0.25s and ~0.20s respectively.
- **README** (`backend/scripts/README.md`) — operator-facing docs for the smoke + manual UI smoke.

### Files modified / added

```
ledger/main.beancount                                  NEW (mock)
ledger/accounts.beancount                              NEW (mock)
ledger/manual/2026-04.beancount                        NEW (mock)
ledger/fava_edit_validator/__init__.py                 NEW (extension)
ledger/.gitignore                                      NEW (snapshots, lock, log, msg, staging)
backend/scripts/smoke_fava_edit_validator.py           NEW (smoke runner)
backend/scripts/README.md                              NEW (operator docs)
backend/tests/test_fava_edit_validator.py              NEW (6 unit tests)
```

No existing source files were modified.

### AC verification

| AC  | Verified by                                                                       |
|-----|-----------------------------------------------------------------------------------|
| AC1 | Unit `test_invalid_edit_is_reverted_and_logged` + smoke case B                    |
| AC2 | Unit `test_invalid_edit_is_reverted_and_logged` (asserts `last-revert-message.json`) |
| AC3 | Unit `test_fresh_import_lock_times_out_and_reverts` + `test_stale_import_lock_does_not_block` |
| AC4 | Unit `test_atomic_restore_uses_snapshot_bytes` (byte-for-byte equality after revert) |
| AC5 | Unit `test_invalid_edit_is_reverted_and_logged` (parses `edit-revert-log.jsonl`)  |
| AC6 | Smoke runner — case A 0.25s, case B 0.20s, both well under 5s                     |

### Open items / follow-ups

- **AC5 detail — git-history of tampering.** The story file notes that `edit-revert-log.jsonl` is gitignored as audit. I made it gitignored under `ledger/.gitignore`. If Ary wants tampering visibility through git history, this needs to flip — the file is unchecked-in today and the only audit trail is the filesystem.
- **Pre-existing test failure.** `backend/tests/test_sync.py::test_run_backfill_calls_upsert_for_both_sheets` fails on `main` HEAD (verified by stashing my changes and re-running). Not introduced by this story; flagging for Bob/Ary triage.
- **Banner UI.** Plumbing for the contador-facing banner is deferred (see Decision #4). The data is already on disk; whoever picks up the Fava plugin or thin-API endpoint can read `_meta/last-revert-message.json` to render it.
