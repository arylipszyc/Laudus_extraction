---
story: 9.9
title: Validación de balances post-import via bean-check (era 4.2)
status: ready-for-dev
epic: 9
depends_on: [9.6]
blocks: []
---

# Story 9.9 — Validación de balances post-import

## User Story

As a contador,
I want closing-balance validation of every imported PDF cartola to be enforced natively by `bean-check` (via `Balance` directives) and to receive a clear UI summary when the validation fails (with a path to override using a written justification),
So that I never confirm a cartola where the math is broken — and when math is genuinely broken, I have an explicit, auditable mechanism to document why I'm overriding.

## Context

Story 4.2 reformulada bajo c4. La validación de balance (FR22-FR25) ahora es responsabilidad nativa de Beancount:
- Story 9.6 emite una `Balance` directive al cierre del período en cada cartola importada.
- `bean-check` corre post-promotion y falla si `opening + Σ tx ≠ closing`.
- Esta story (9.9) provee:
  - El endpoint `PATCH /api/v1/cartolas/{batch_id}/validate-balance` que orquesta el promote (de staging a archivo final) + bean-check + commit.
  - El UI summary que muestra discrepancia + permite override con justificación.
  - El flujo de override: convierte la `Balance` en `pad`+`balance` con metadata (Story 9.6 ya implementa la conversion function).

## Acceptance Criteria

**AC1 — `PATCH /api/v1/cartolas/{batch_id}/validate-balance` (path normal)**

**Given** un staging file existe (`_staging/{batch_id}.cartola.json` de Story 9.5) y el contador confirmó los balances
**When** se llama el endpoint con `{"opening": ..., "closing": ..., "override_justification": null}`
**Then** el backend:
  1. Si los `opening`/`closing` enviados difieren del JSON canónico original → actualizan el staging JSON
  2. Llama `CartolaPdfImporter.promote(batch_id)` (Story 9.6 Task 6)
  3. La promoción incluye correr `bean-check` → si OK: archivo final + commit + push
  4. Response: `{"status": "validated", "file": "imports/cartolas/{slug}.beancount", "git_sha": "..."}`
**And** si `bean-check` falla por discrepancia de balance → response `{"status": "discrepancy", "diff": ..., "calculated": ..., "stated": ...}` y el archivo final NO se crea (staging persiste)

---

**AC2 — UI: discrepancy indicator real-time**

**Given** la pantalla `CartolaUploadPage.tsx` muestra el resultado del upload + 3 fields editables
**When** el contador edita opening o closing
**Then** se calcula client-side: `discrepancy = closing - opening - Σ transactions`
**And** se muestra el valor en tiempo real
**And** botón "Confirmar validación" se habilita solo si `discrepancy === 0` o si justificación está provista (override flow AC4)

---

**AC3 — Confirmación happy path (AC1 wrapper UI)**

**Given** discrepancy = 0
**When** el contador clickea "Confirmar validación"
**Then** se dispara `PATCH .../validate-balance` con `override_justification: null`
**And** loading indicator hasta respuesta
**And** post-success: navegar a categorización pendiente o mostrar resumen "Cartola importada — N transacciones, M pendientes de categorizar"

---

**AC4 — Override flow con justificación (FR25)**

**Given** discrepancy ≠ 0 y el contador no puede resolverla editando opening/closing
**When** clickea "Override con justificación"
**Then** aparece textarea obligatoria
**And** botón "Confirmar override" se habilita solo si justificación tiene ≥ 20 caracteres
**And** click dispara `PATCH .../validate-balance` con `override_justification: "..."`
**And** el backend pasa la justificación a `convert_balance_to_pad(...)` (Story 9.6 Task 5) → re-promote con pad+balance + metadata
**And** post-success: la promotion completa con bean-check OK; commit + push
**And** la metadata `override_justification`, `override_user`, `override_at` queda registrada en la directiva Beancount

---

**AC5 — Endpoint rechaza override sin justificación cuando hay discrepancia**

**Given** discrepancy ≠ 0 y `override_justification` es null/empty
**When** se llama `PATCH .../validate-balance`
**Then** response HTTP 400 con `{"error": {"code": "VALIDATION_FAILED", "message": "Discrepancia detectada — provea override_justification para confirmar", "diff": ...}}`
**And** no commit, staging persiste

---

**AC6 — Audit trail del override en git history**

**Given** un override completó exitosamente
**When** revisamos `git log -p -- ledger/imports/cartolas/{slug}.beancount`
**Then** el commit muestra la directiva `pad` + `balance` con metadata completa (`override_justification`, `override_user`, `override_at`)
**And** el commit message es: `[importer-cartola] {bank} {YYYY-MM}: +N tx, OVERRIDE pad+balance`

---

**AC7 — Frontend muestra warnings extraction (de Story 9.5)**

**Given** el JSON canónico tiene `extraction.warnings[]` (de Story 9.5)
**When** la UI renderiza
**Then** muestra cada warning con su `code`, `line_no` (si aplica), `detail` en una sección "⚠ Avisos de extracción"
**And** los warnings NO bloquean confirmación; son informativos

---

**AC8 — Tests integración**

**Given** un fixture cartola con balance OK (cuadra)
**When** se sube + valida
**Then** archivo final creado + commit + bean-check pasa

**Given** un fixture cartola con balance NO cuadra
**When** se sube + se intenta confirmar sin justificación
**Then** response 400 con discrepancia detallada

**Given** un fixture cartola con balance NO cuadra y se override con justificación válida
**When** se confirma
**Then** archivo final creado con pad+balance + metadata + bean-check pasa

---

## Tasks / Subtasks

- [ ] Task 1: Endpoint `PATCH /api/v1/cartolas/{batch_id}/validate-balance`
  - [ ] Crear `backend/app/api/v1/cartolas/router.py` (o adaptar el existente de Story 9.5)
  - [ ] Schema request: `{"opening": float, "closing": float, "override_justification": str | null}`
  - [ ] Update staging JSON con opening/closing si difieren
  - [ ] Invocar `CartolaPdfImporter.promote(batch_id)` (Story 9.6)
  - [ ] Manejar 3 paths: OK, discrepancy sin override, discrepancy con override
  - [ ] RBAC: `require_role(["contador"])`

- [ ] Task 2: Discrepancy indicator client-side
  - [ ] Componente `<BalanceValidationPanel cartola={canonical}>` en `CartolaUploadPage.tsx`
  - [ ] 3 fields: opening (editable, pre-filled), Σ tx (read-only, calculado en JS), closing (editable, pre-filled)
  - [ ] Realtime indicator: discrepancia number + color (verde si 0, rojo si ≠)
  - [ ] Botón "Confirmar" disabled-when-discrepancy

- [ ] Task 3: Override flow UI
  - [ ] Toggle "No puedo cuadrar — override con justificación"
  - [ ] Textarea con counter de caracteres + minlength 20
  - [ ] Botón "Confirmar override" gateado por longitud

- [ ] Task 4: Renderizar warnings extraction
  - [ ] Sección con lista de warnings (chips amber)
  - [ ] Tooltip detalle por warning

- [ ] Task 5: Backend service `validate_balance(batch_id, opening, closing, override_justification)`
  - [ ] Update staging file JSON in-place (atomic)
  - [ ] Llamar a `CartolaPdfImporter.promote`
  - [ ] Si bean-check falla:
    - Si `override_justification` provided: invocar `convert_balance_to_pad` + re-intentar promote
    - Si NO: rollback, retornar shape de discrepancia
  - [ ] Si OK: retornar success con git_sha del commit

- [ ] Task 6: Tests
  - [ ] Unit: discrepancy calculation client-side
  - [ ] Integration backend: 3 paths (OK, discrepancy, override) con fixture JSON canónicos sintéticos
  - [ ] Integration full: subir PDF mock → 9.5 produce JSON → 9.9 valida → archivo final + bean-check OK

---

## Dev Notes

### Input autoritativo

`architecture-c4.md` §4.2 — Balance directive como mecanismo de validación + override pad+balance. Story 9.6 §AC5 y §AC6 + Task 5 implementan la lógica de conversión.

### Reemplaza la lógica custom de FR22-FR25

El approach de Story 4.2 original era validar discrepancias en la base de datos (Supabase `cartola_batches`) con código custom. Bajo c4, todo es delegado a Beancount: emit `Balance` → `bean-check` valida → si falla, conversion a `pad` documenta el override en metadata. Más limpio y auditable.

### Out of scope

- Validación de items individuales (FR26 duplicate, FR27 anomalous) — es trabajo de Story 9.5 (warnings) ya cubierto.
- Cambiar la lógica de Beancount (`bean-check`) — es OSS, lo usamos como está.

### Project structure

```
backend/app/api/v1/cartolas/
  router.py                                # MODIFY (de 9.5) — agregar PATCH /validate-balance
  service.py                               # MODIFY — método validate_balance
frontend/src/
  pages/CartolaUploadPage.tsx              # MODIFY (de 9.5) — agregar BalanceValidationPanel
  components/BalanceValidationPanel.tsx    # NEW
```

### References

- [Source: architecture-c4.md §4.2 — Balance directive + override pad+balance]
- [Source: 9-6-beangulp-importer-json-to-directivas.md — Task 5 + AC6]
- [Source: epics.md Story 4.2 original]
