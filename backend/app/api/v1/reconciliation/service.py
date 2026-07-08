"""Lectura/resolución de discrepancias de reconciliación — Story 9.12.

Fuente única: `ledger/_meta/cartola-discrepancies.jsonl` (emitido por 9.6b, sin Supabase).
Parseo lazy line-by-line + filtros in-memory. Una discrepancia está RESUELTA si existe una
línea de resolución (`ref_discrepancy_id`) que la referencia — esas se ocultan del dashboard
(quedan como audit trail, accesibles vía history).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Estados bloqueantes (chip rojo, AC9): valor que no cuadra (no se importa) o FX fuera de tolerancia.
BLOCKING_STATES = {"value-mismatch", "fx-out-of-tolerance"}

# Acciones permitidas por estado (AC4). `escalate` no cierra la discrepancia.
ACTIONS_BY_STATE = {
    "value-mismatch": {"accept-cartola", "accept-laudus", "escalate"},
    "missing-in-laudus": {"confirm-cartola-only", "escalate"},
    "missing-in-cartola": {"confirm-laudus-only", "escalate"},
    "date-mismatch": {"accept-cartola-date", "accept-laudus-date", "escalate"},
    "description-mismatch": {"accept-cartola-description", "accept-laudus-description", "merge", "escalate"},
    "category-mismatch": {"accept-cartola-category", "accept-laudus-category", "manual-category", "escalate"},
    "fx-out-of-tolerance": {"accept-derived-fx", "accept-bcch-fx", "manual-fx", "escalate"},
}


# Tope defensivo de ids por batch (Story 6.7 — decisión Ary): el costo real no escala con N
# (un solo bean_check/push), pero se acota payload/render/tamaño del commit. 422 si se excede.
MAX_BATCH = 50


class ResolveError(Exception):
    """Acción inválida o justificación faltante (HTTP 400)."""


class AnnotationFailed(Exception):
    """La anotación al ledger falló (p.ej. bean-check rojo) → no se cierra la discrepancia (HTTP 422)."""


def _jsonl_path() -> Path:
    override = os.getenv("LEDGER_DISCREPANCIES")
    if override:
        return Path(override)
    ledger_dir = os.getenv("LEDGER_DIR")
    root = Path(ledger_dir) if ledger_dir else Path(__file__).resolve().parents[5] / "ledger"
    return root / "_meta" / "cartola-discrepancies.jsonl"


def _runs_path() -> Path:
    """Ruta del JSONL de run-records (Story 6.5) — espejo de `_jsonl_path`."""
    override = os.getenv("LEDGER_RECONCILIATION_RUNS")
    if override:
        return Path(override)
    ledger_dir = os.getenv("LEDGER_DIR")
    root = Path(ledger_dir) if ledger_dir else Path(__file__).resolve().parents[5] / "ledger"
    return root / "_meta" / "reconciliation-runs.jsonl"


def _iter_lines(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _year_month(entry: dict) -> str:
    # Story 6.5b: el período del ESTADO DE CUENTA es un campo persistido (distinto de la fecha de
    # la tx). Se prefiere; las discrepancias viejas sin el campo caen al derivado de la fecha.
    persisted = entry.get("year_month")
    if persisted:
        return str(persisted)
    for side in ("cartola", "laudus"):
        d = (entry.get(side) or {}).get("date")
        if d:
            return str(d)[:7]
    return ""


def _resolved_ids(path: Path) -> set[str]:
    """IDs con resolución que CIERRA la discrepancia. `escalate` no cierra (AC4) → no cuenta."""
    out = set()
    for e in _iter_lines(path):
        res = e.get("resolution")
        if e.get("ref_discrepancy_id") and res is not None and res.get("action") != "escalate":
            out.add(e["ref_discrepancy_id"])
    return out


def _is_original(entry: dict) -> bool:
    return entry.get("discrepancy_id") is not None and "ref_discrepancy_id" not in entry


def read_discrepancies(*, state=None, year_month=None, bank_account_id=None,
                       discrepancy_id=None, path: Path | None = None) -> dict:
    """Discrepancias sin resolver (o una específica por id, incluso resuelta) + summary (AC1)."""
    path = path or _jsonl_path()
    resolved = _resolved_ids(path)
    items, by_state = [], {}
    for e in _iter_lines(path):
        if not _is_original(e):
            continue
        if discrepancy_id is not None:
            if e["discrepancy_id"] == discrepancy_id:
                items.append({**e, "year_month": _year_month(e)})
            continue
        if e["discrepancy_id"] in resolved:
            continue
        if bank_account_id and e.get("bank_account_id") != bank_account_id:
            continue
        if year_month and _year_month(e) != year_month:
            continue
        # El summary cuenta por estado SIN aplicar el filtro `state`, para que los chips de los
        # demás estados sigan visibles al filtrar por uno (si no, la UI los pierde).
        by_state[e.get("state")] = by_state.get(e.get("state"), 0) + 1
        if state and e.get("state") != state:
            continue
        items.append({**e, "year_month": _year_month(e)})
    total = len(items) if discrepancy_id is not None else sum(by_state.values())
    return {"discrepancies": items, "summary": {"total": total, "by_state": by_state}}


def history(discrepancy_id: str, path: Path | None = None) -> list[dict]:
    """Todas las líneas con ese discrepancy_id (original + resoluciones), en orden de archivo (AC2)."""
    path = path or _jsonl_path()
    out = []
    for e in _iter_lines(path):
        if e.get("discrepancy_id") == discrepancy_id or e.get("ref_discrepancy_id") == discrepancy_id:
            out.append(e)
    return out


def pending_count(path: Path | None = None) -> dict:
    """{total, blocking} de las discrepancias sin resolver (AC9 — color del chip)."""
    data = read_discrepancies(path=path)
    total = data["summary"]["total"]
    blocking = sum(n for st, n in data["summary"]["by_state"].items() if st in BLOCKING_STATES)
    return {"total": total, "blocking": blocking}


def list_periods(path: Path | None = None, runs_path: Path | None = None) -> list[dict]:
    """Estado por (cuenta, mes): cruza el último run-record con las discrepancias abiertas (Story 6.5).

    AC3/AC4/AC5: agrupa los run-records por (bank_account_id, year_month) tomando el más reciente por
    `reconciled_at` (append-only, último gana en el lector). `open` se deriva en vivo del JSONL de
    discrepancias reusando `read_discrepancies(...).summary.total` — que ya excluye resueltas/escaladas
    y filtra por el `year_month` PERSISTIDO (6.5b), no por la fecha de la tx → cuadra con el run-record.
    `status` = "complete" si `open == 0`, "pending" si `open > 0`. Orden: mes desc, cuenta asc.
    """
    runs_path = runs_path or _runs_path()
    disc_path = path or _jsonl_path()
    latest: dict[tuple, dict] = {}
    for r in _iter_lines(runs_path):
        ym = r.get("year_month")
        if not ym:
            continue
        key = (r.get("bank_account_id"), ym)
        prev = latest.get(key)
        if prev is None or str(r.get("reconciled_at") or "") >= str(prev.get("reconciled_at") or ""):
            latest[key] = r

    periods = []
    for (bank_account_id, ym), r in latest.items():
        open_count = read_discrepancies(
            bank_account_id=bank_account_id, year_month=ym, path=disc_path)["summary"]["total"]
        periods.append({
            "bank_account_id": bank_account_id,
            "year_month": ym,
            "reconciled_at": r.get("reconciled_at"),
            "matched": r.get("matched", 0),
            "differences": r.get("differences", 0),
            "open": open_count,
            "status": "complete" if open_count == 0 else "pending",
        })
    periods.sort(key=lambda p: str(p["bank_account_id"] or ""))      # cuenta asc (secundario)
    periods.sort(key=lambda p: p["year_month"], reverse=True)        # mes desc (primario, estable)
    return periods


def resolve(discrepancy_id: str, action: str, justification: str | None,
            *, user_email: str, now_iso: str, path: Path | None = None,
            category_account: str | None = None, ledger_root=None, importer=None) -> dict:
    """Valida la acción vs el estado y appendea la resolución al JSONL (AC3/AC4).

    **Story 6.3 (modelo A):** si la acción es `confirm-cartola-only` sobre un `missing-in-laudus`
    (un gasto real que está en la cartola pero no en Laudus), ANTES de cerrar la discrepancia se
    anota la transacción al ledger (`annotate_discrepancy` → zona `manual/`, bean-check + git).
    Orden = anotar → si OK → `append_resolution` (atomicidad AC2: nunca una discrepancia "resuelta"
    sin su tx, ni una tx sin cerrar la discrepancia). Las demás acciones se comportan como antes
    (solo audit trail, sin tocar el ledger).
    """
    from pipeline.importers.discrepancy_writer import append_resolution

    path = path or _jsonl_path()
    # encontrar la discrepancia original para conocer su estado
    original = next((e for e in _iter_lines(path)
                     if _is_original(e) and e["discrepancy_id"] == discrepancy_id), None)
    if original is None:
        raise ResolveError(f"discrepancy_id {discrepancy_id} no existe")
    if discrepancy_id in _resolved_ids(path):  # AC6: guard ANTES de escribir al ledger
        raise ResolveError(f"discrepancy_id {discrepancy_id} ya fue resuelta")
    state = original.get("state")
    # `escalate` no cierra y sirve para cualquier estado (incl. fx-bcch-missing/fx-implausible que
    # 9.6b emite y no están en la tabla) → siempre permitido, evita dead-ends. El resto se valida.
    if action != "escalate" and action not in ACTIONS_BY_STATE.get(state, set()):
        raise ResolveError(f"acción '{action}' no permitida para estado '{state}'")
    if action != "escalate" and (not justification or len(justification.strip()) < 10):
        raise ResolveError("justification ≥ 10 caracteres requerida (excepto escalate)")

    # AC1/AC2: la única acción que ESCRIBE al ledger es confirmar una línea de cartola ausente de
    # Laudus. Se anota antes de cerrar; si la anotación falla, la discrepancia queda abierta.
    git_commit_sha = None
    if state == "missing-in-laudus" and action == "confirm-cartola-only":
        from pipeline.importers.laudus_run import _ledger_root
        from pipeline.importers.reconcile import annotate_discrepancy

        root = ledger_root or _ledger_root()
        if importer is None:
            from backend.app.api.v1.cartolas.service import _build_importer
            importer = _build_importer(root)
        res = annotate_discrepancy(original, category_account=category_account,
                                   importer=importer, ledger_root=root, ts=now_iso)
        if not res.get("success"):
            raise AnnotationFailed(res.get("error_msg") or "no se pudo anotar la transacción")
        git_commit_sha = res.get("git_commit_sha")

    resolution = {"action": action, "resolved_by": user_email, "resolved_at": now_iso,
                  "justification": (justification or "").strip()}
    if action == "escalate":
        resolution["escalated_at"] = now_iso  # no cierra la discrepancia
    append_resolution(discrepancy_id, resolution, path)
    return {"status": "escalated" if action == "escalate" else "resolved",
            "discrepancy_id": discrepancy_id, "action": action, "git_commit_sha": git_commit_sha}


def resolve_batch(items: list[dict], *, justification: str | None, user_email: str, now_iso: str,
                  path: Path | None = None, ledger_root=None, importer=None) -> dict:
    """Resuelve N discrepancias como UNA unidad transaccional (Story 6.7) — un `bean_check` + un commit.

    `items` = `[{discrepancy_id, action, category_account?}]`. `justification` es COMÚN al batch
    (decisión Ary): se valida ≥10 (salvo que TODAS las acciones sean `escalate`) y se registra igual en
    cada resolución. Orden todo-o-nada, heredado de 6.3 AC2:
      1. Preflight (AC6): mismos guards que `resolve` — existe / ya-resuelta / `ACTIONS_BY_STATE` /
         justificación — con UNA lectura del JSONL; ids duplicados intra-batch → rechazo; tope `MAX_BATCH`.
         Si CUALQUIER item falla → nada se escribe ni se cierra.
      2. Anotaciones (`missing-in-laudus` + `confirm-cartola-only`) → `annotate_discrepancies_batch`
         (render-all valida datos/cuenta/FX antes de escribir; un solo bean_check + commit; rollback total).
      3. Solo si el motor devolvió `success` (o no había nada que anotar) → `append_resolution` de TODAS.
    """
    from pipeline.importers.discrepancy_writer import append_resolution

    path = path or _jsonl_path()
    if not items:
        raise ResolveError("el batch no tiene items")
    if len(items) > MAX_BATCH:
        raise ResolveError(f"el batch excede el máximo de {MAX_BATCH} items ({len(items)})")

    ids = [it["discrepancy_id"] for it in items]
    if len(set(ids)) != len(ids):  # todo-o-nada también en la validación: ids repetidos → rechazo
        raise ResolveError("hay discrepancy_id duplicados en el batch")

    # UNA lectura del JSONL: originales por id + set de resueltas (mismo criterio que `_resolved_ids`).
    lines = list(_iter_lines(path))
    originals = {e["discrepancy_id"]: e for e in lines if _is_original(e)}
    resolved: set[str] = set()
    for e in lines:
        res = e.get("resolution")
        if e.get("ref_discrepancy_id") and res is not None and res.get("action") != "escalate":
            resolved.add(e["ref_discrepancy_id"])

    all_escalate = all(it["action"] == "escalate" for it in items)
    if not all_escalate and (not justification or len(justification.strip()) < 10):
        raise ResolveError("justification ≥ 10 caracteres requerida (excepto batch todo-escalate)")

    # Preflight por item (AC6): un id inválido aborta el batch entero antes de escribir nada.
    annotate_items: list[tuple[dict, str | None]] = []
    for it in items:
        did, action = it["discrepancy_id"], it["action"]
        original = originals.get(did)
        if original is None:
            raise ResolveError(f"discrepancy_id {did} no existe")
        if did in resolved:  # AC6/AC5: guard ANTES de escribir al ledger
            raise ResolveError(f"discrepancy_id {did} ya fue resuelta")
        state = original.get("state")
        if action != "escalate" and action not in ACTIONS_BY_STATE.get(state, set()):
            raise ResolveError(f"acción '{action}' no permitida para estado '{state}'")
        if state == "missing-in-laudus" and action == "confirm-cartola-only":
            annotate_items.append((original, it.get("category_account")))

    # Motor batch para las anotaciones: un solo bean_check + un solo commit, rollback total.
    git_commit_sha = None
    if annotate_items:
        from pipeline.importers.laudus_run import _ledger_root
        from pipeline.importers.reconcile import annotate_discrepancies_batch

        root = ledger_root or _ledger_root()
        if importer is None:
            from backend.app.api.v1.cartolas.service import _build_importer
            importer = _build_importer(root)
        res = annotate_discrepancies_batch(annotate_items, importer=importer, ledger_root=root, ts=now_iso)
        if not res.get("success"):
            raise AnnotationFailed(res.get("error_msg") or "no se pudo anotar el batch")
        git_commit_sha = res.get("git_commit_sha")

    # Solo tras el push OK (o si no había nada que anotar) → cerrar TODAS (anotadas + baratas).
    results = []
    for it in items:
        did, action = it["discrepancy_id"], it["action"]
        resolution = {"action": action, "resolved_by": user_email, "resolved_at": now_iso,
                      "justification": (justification or "").strip()}
        if action == "escalate":
            resolution["escalated_at"] = now_iso  # no cierra la discrepancia
        append_resolution(did, resolution, path)
        annotated = (originals[did].get("state") == "missing-in-laudus"
                     and action == "confirm-cartola-only")
        results.append({"status": "escalated" if action == "escalate" else "resolved",
                        "discrepancy_id": did, "action": action,
                        "git_commit_sha": git_commit_sha if annotated else None})
    return {"git_commit_sha": git_commit_sha, "results": results}
