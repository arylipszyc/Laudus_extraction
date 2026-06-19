# Dashboard de reconciliación (Story 9.12)

Vista accionable sobre las diferencias entre lo extraído de la cartola y lo registrado en
Laudus. Fuente única: `ledger/_meta/cartola-discrepancies.jsonl` (emitido por el motor de
matching de 9.6b, sin Supabase).

## Para el contador

1. **Chip del header** (`⚠ N reconciliaciones`): aparece cuando hay diferencias sin resolver.
   - **Amber**: todas no-bloqueantes (revisar cuando puedas).
   - **Rojo**: hay ≥1 bloqueante (`value-mismatch` = un monto que no cuadra y NO se importó, o
     `fx-out-of-tolerance` = la FX derivada se aleja >5% del dólar BCCh). El tooltip dice cuántas.
   - Click → `/reconciliation`.
2. **Página `/reconciliation`**: chips por estado (clickeables para filtrar) + tabla.
3. **Revisar una diferencia** → panel de detalle: cartola vs Laudus lado a lado, cálculo FX, y los
   **botones de acción** según el estado (ver tabla). Toda acción (salvo *escalate*) pide una
   **justificación ≥10 caracteres** que queda en el audit trail.

## Acciones por estado

| Estado | Acciones |
|---|---|
| value-mismatch | accept-cartola · accept-laudus · escalate |
| missing-in-laudus | confirm-cartola-only · escalate |
| missing-in-cartola | confirm-laudus-only · escalate |
| date-mismatch | accept-cartola-date · accept-laudus-date · escalate |
| description-mismatch | accept-cartola-description · accept-laudus-description · merge · escalate |
| category-mismatch | accept-cartola-category · accept-laudus-category · manual-category · escalate |
| fx-out-of-tolerance | accept-derived-fx · accept-bcch-fx · manual-fx · escalate |

`escalate` no cierra la diferencia — solo la marca para seguimiento (sigue visible). El resto la
resuelve: se appendea la resolución al JSONL y desaparece del dashboard.

## Endpoints (RBAC contador/admin)

- `GET /api/v1/reconciliation/discrepancies?state=&year_month=&bank_account_id=&discrepancy_id=`
- `GET /api/v1/reconciliation/history/{discrepancy_id}` — audit trail completo (original + resoluciones).
- `GET /api/v1/reconciliation/count` → `{total, blocking}` (alimenta el color del chip).
- `POST /api/v1/reconciliation/discrepancies/{discrepancy_id}/resolve` `{action, justification}`.

## Re-emit del `.beancount` (seam con 9.6b)

La resolución se registra (audit trail) y la diferencia se oculta. El **re-emit del archivo de
cartola** ajustado por acción se apoya en `reconcile.commit_reconciliation` (Story 9.6b) y se
activa cuando el flujo de upload de cartolas pase a usar el motor de reconciliación en vivo (seam
documentado en 9.6b). Hasta entonces el dashboard registra/escala las diferencias del JSONL.
