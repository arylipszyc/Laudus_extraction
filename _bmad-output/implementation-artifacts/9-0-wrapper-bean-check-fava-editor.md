---
story: 9.0
title: Wrapper bean-check para Fava editor
status: ready-for-dev
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

- [ ] Task 1: Investigación técnica — elegir mecanismo de wrapping
  - [ ] **Opción A — Fava extension oficial:** investigar la API de extensions de Fava (`fava.ext.FavaExtension`) y verificar si hooks pre-save/post-save existen. Buscar en `https://fava.pythonanywhere.com/example-source/help/extensions/` o repo `beancount/fava` GitHub.
  - [ ] **Opción B — Filesystem watcher externo:** proceso separado que usa `watchfiles` para detectar cambios en `ledger/`, distingue cambios del editor Fava (path = ledger files) de cambios del importer (path = imports/laudus|cartolas), corre `bean-check`, revierte si falla.
  - [ ] **Opción C — Wrapper de Fava (proxy):** monkeypatch del endpoint de save de Fava para inyectar la validación antes del write final. Más invasivo, frágil ante updates de Fava.
  - [ ] Decidir entre A/B/C y documentar trade-offs en Dev Notes. **Criterio de decisión:** robustez ante updates de Fava > simplicidad. Default recomendado: B (filesystem watcher externo + atomic rename) si A no expone el hook necesario.

- [ ] Task 2: Implementar el wrapper (según opción elegida)
  - [ ] Crear `backend/scripts/fava_edit_validator.py` (o módulo equivalente según opción).
  - [ ] Pre-edit: leer y stashear contenido del archivo a editar (snapshot en `tempfile`).
  - [ ] Post-edit: correr `bean-check ledger/main.beancount` via `subprocess.run` con timeout 30s; capturar stdout/stderr.
  - [ ] Si exit-code ≠ 0: restore desde snapshot via `os.replace` (atómico). Si exit-code = 0: confirmar (descartar snapshot).

- [ ] Task 3: Integración con lock file
  - [ ] Antes de validar: chequear `ledger/.import.lock`. Si existe y `mtime` < 5min → wait con polling cada 1s, max 60s. Si timeout → abort con error visible al contador.
  - [ ] Mientras corre la validación: NO tomar el lock (los importers son los que escriben en zonas distintas; el contador solo escribe en `manual/` o `accounts.beancount`). Solo serializa contra otros edits del propio contador y contra importers para evitar `bean-check` race.

- [ ] Task 4: Audit log de reverts
  - [ ] Definir formato de línea JSONL en `ledger/_meta/edit-revert-log.jsonl`:
    ```json
    {"ts": "2026-04-30T15:32:11Z", "file": "manual/2026-04.beancount",
     "pre_hash": "sha256:abc...", "post_hash": "sha256:def...",
     "user": "contador@ammy.cl", "bean_check_error": "..."}
    ```
  - [ ] Asegurar que el archivo `edit-revert-log.jsonl` NO esté incluido en los `include` de `main.beancount` (queda como pure audit, sin afectar el ledger).
  - [ ] Asegurar permisos: append-only desde el punto de vista del wrapper; un contador no puede borrar líneas (es un archivo del filesystem, file mode 644 alcanza — lo que importa es que git history captura tampering).

- [ ] Task 5: Mensaje al contador
  - [ ] Si la opción elegida es A (Fava extension): inyectar banner Fava con `flash`-equivalent de la extension API.
  - [ ] Si la opción es B/C: escribir el mensaje a un archivo `ledger/_meta/last-revert-message.txt` (o equivalente) que Fava lea como markdown via plugin de "documentos" (Fava soporta) o vía un endpoint custom del thin API que el frontend de Fava muestre. Si ninguna funciona limpio: el contador ve el revert porque el archivo cambió + la línea de log; el banner queda como nice-to-have v2.

- [ ] Task 6: Smoke test end-to-end
  - [ ] Caso 1: edit válido (renombrar narration) → bean-check pasa → archivo se preserva. Timing < 5s.
  - [ ] Caso 2: edit que rompe (cambiar amount de un posting) → bean-check falla → archivo revertido + línea en log. Timing < 5s.
  - [ ] Caso 3: lock file activo (importer corriendo simulado) → edit espera → procede tras release. Sin race.
  - [ ] Documentar el smoke test en `backend/scripts/README.md` para que F2 (Story 9.3 deploy) lo corra como gate.

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
