"""Comportamiento por estado de matching — Story 9.6b AC4/AC3.

Convierte un `MatchResult` (+ `FXResult` opcional) en una decisión de emisión:
si emitir la Transaction, con qué flag, y qué discrepancia(s) registrar en el JSONL.
La construcción de la Transaction beancount la hace el importer (9.6a); acá solo se
decide QUÉ hacer.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable

from pipeline.importers.discrepancy_writer import build_discrepancy
from pipeline.importers.fx_calculator import FXResult, calculate_fx, lookup_bcch
from pipeline.importers.matching_engine import (
    DATE_TOLERANCE_DAYS,
    USD_FX_EPOCH,
    CartolaLine,
    LaudusEntry,
    MatchResult,
    match,
)

# Estados que NO emiten Transaction (bloqueantes hasta resolución manual via 9.12).
# missing-in-cartola: la cartola es la fuente de verdad → el asiento que solo está en Laudus
# no se contabiliza (evita doble conteo vs imports/laudus/*); se muestra como discrepancia
# para que 9.12 lo despliegue y ofrezca borrarlo (decisión Ary 2026-06-17).
_BLOCKING = {"value-mismatch", "missing-in-cartola"}
_FX_FLAG_STATES = {"fx-out-of-tolerance", "fx-bcch-missing", "fx-implausible"}


@dataclass
class ProcessDecision:
    emit: bool                       # ¿emitir la Transaction?
    flag: str | None                 # "*" | "!" | None (si no se emite)
    discrepancies: list[dict] = field(default_factory=list)


def _num(x: Decimal | None):
    return float(x) if x is not None else None


def _cartola_dict(mr: MatchResult) -> dict | None:
    cl = mr.cartola_line
    if cl is None:
        return None
    return {"line_no": cl.line_no, "date": cl.date.isoformat(), "amount": _num(cl.amount),
            "currency": cl.currency, "description": cl.description}


def _laudus_dict(mr: MatchResult) -> dict | None:
    le = mr.laudus_entry
    if le is None:
        return None
    return {"journal_entry_id": le.je_id, "date": le.date.isoformat(),
            "amount": _num(le.amount), "currency": le.currency, "description": le.description}


def _fx_dict(fx: FXResult | None) -> dict:
    if fx is None:
        return {"implied": None, "bcch": None, "deviation_pct": None}
    return {"implied": _num(fx.implied), "bcch": _num(fx.bcch), "deviation_pct": _num(fx.deviation_pct)}


def process_match_result(
    mr: MatchResult,
    fx: FXResult | None,
    *,
    batch_id: str,
    bank_account_id: str,
    ts: str,
    year_month: str | None = None,
) -> ProcessDecision:
    """Decisión de emisión + discrepancias para un MatchResult (AC4) + overlay FX (AC3).

    `year_month` (6.5b): período del estado de cuenta, se persiste en cada discrepancia.
    """
    def _disc(state: str) -> dict:
        # AC4: source = lado que tiene el dato cuando el otro falta.
        source = "cartola" if mr.laudus_entry is None else ("laudus" if mr.cartola_line is None else None)
        return build_discrepancy(
            batch_id=batch_id, bank_account_id=bank_account_id, state=state, ts=ts,
            cartola=_cartola_dict(mr), laudus=_laudus_dict(mr), fx=_fx_dict(fx), source=source,
            year_month=year_month,
        )

    discrepancies: list[dict] = []

    if mr.state in _BLOCKING:
        # No se emite Transaction; solo discrepancia bloqueante.
        return ProcessDecision(emit=False, flag=None, discrepancies=[_disc(mr.state)])

    if mr.state == "perfect":
        emit, flag = True, "*"
    else:
        emit, flag = True, "!"
        discrepancies.append(_disc(mr.state))

    # Overlay FX (AC3): una desviación/ausencia/implausibilidad fuerza flag ! + discrepancia FX,
    # incluso si el match era 'perfect'.
    if fx is not None and fx.state in _FX_FLAG_STATES:
        flag = "!"
        discrepancies.append(_disc(fx.state))

    return ProcessDecision(emit=emit, flag=flag, discrepancies=discrepancies)


# ── Orquestador: cartola + Laudus → (entries beancount, discrepancias) (AC1-AC9) ──


def reconcile_and_build(
    *,
    cartola_lines: list[CartolaLine],
    laudus_entries: list[LaudusEntry],
    period_start: date,
    account_target: str,
    is_liability: bool,
    category_for: Callable[[CartolaLine], str],
    fx_jsonl_path,
    bank_slug: str,
    year_month: str,
    batch_id: str,
    bank_account_id: str,
    ts: str,
):
    """Corre el matching y arma (entries beancount, discrepancias) según el comportamiento por
    estado. USD (era FX, period_start ≥ 2026) emite con price per-unit + metadata FX; pre-2026
    es CLP-only (AC9). value-mismatch NO emite. missing-in-cartola emite desde Laudus CLP-only.
    """
    from beancount.core import data
    from beancount.core.amount import Amount
    from pipeline.importers.cartola_pdf_importer import _build_postings, build_usd_postings, fx_metadata

    fx_era = period_start >= USD_FX_EPOCH
    results = match(cartola_lines, laudus_entries, period_start=period_start)
    entries: list = []
    discrepancies: list[dict] = []

    for mr in results:
        cl = mr.cartola_line
        fx = None
        if cl is not None and fx_era and cl.currency != "CLP":
            bcch = lookup_bcch(fx_jsonl_path, year_month)
            if mr.laudus_entry is not None:
                # FX implícita per-línea = CLP_laudus / USD_cartola (AC2, Opción D).
                fx = calculate_fx(cl.amount, mr.laudus_entry.amount, bcch)
            elif bcch is not None:
                # USD huérfana (sin contraparte Laudus) → FX de la cartola = BCCh del mes
                # (decisión Ary 2026-06-17). Sin BCCh no se puede contabilizar (abajo).
                fx = FXResult(implied=bcch, bcch=bcch, deviation_pct=Decimal("0"), state=None)
            else:
                fx = FXResult(implied=None, bcch=None, deviation_pct=None, state="fx-bcch-missing")

        decision = process_match_result(mr, fx, batch_id=batch_id, bank_account_id=bank_account_id, ts=ts,
                                        year_month=year_month)
        discrepancies.extend(decision.discrepancies)
        if not decision.emit:
            continue
        # No contabilizar un USD sin tasa (huérfana sin BCCh): solo queda la discrepancia.
        if fx_era and cl.currency != "CLP" and (fx is None or fx.implied is None):
            continue

        # Solo emiten líneas de cartola (la cartola es la fuente de verdad; missing-in-cartola
        # es bloqueante y no llega acá).
        category = category_for(cl)
        meta = {"source": "cartola-pdf", "bank_account_id": bank_account_id, "line": str(cl.line_no)}
        if mr.state == "category-mismatch":
            meta["suggested_category"] = cl.suggested_category
        if fx is not None and fx.implied is not None:
            meta.update(fx_metadata(fx, bank_slug, year_month))
            postings = build_usd_postings(account_target, category, cl.amount, fx.implied, is_liability)
        else:
            postings = _build_postings(account_target, category, cl.amount, cl.currency, is_liability)
        narration, when = cl.description or f"line {cl.line_no}", cl.date

        bmeta = data.new_metadata("<reconcile>", cl.line_no)
        bmeta.update(meta)
        entries.append(data.Transaction(
            meta=bmeta, date=when, flag=decision.flag, payee=None, narration=narration,
            tags=frozenset(), links=frozenset(), postings=postings,
        ))

    return entries, discrepancies


# ── Re-emit post-resolución (AC6) ─────────────────────────────────────────────


def commit_reconciliation(file_path, new_content: str, discrepancy_id: str, action: str, ledger_root) -> dict:
    """Re-genera (write-and-replace) un archivo de cartola tras una resolución (Story 9.12).

    bean-check antes de commitear (rollback si rojo); commit `[reconciliation] resolve {id}: {action}`
    + push, bajo el mismo lock que el importer. `new_content` lo provee el flujo de resolución de 9.12.
    """
    from pathlib import Path

    from pipeline.importers.laudus_run import acquire_lock, bean_check, git_commit_push

    root = Path(ledger_root)
    path = Path(file_path)
    main_path = root / "main.beancount"
    lock_path = root / ".import.lock"
    result = {"discrepancy_id": discrepancy_id, "action": action, "file": str(path),
              "success": False, "error_msg": None, "git_commit_sha": None}

    with acquire_lock(lock_path):
        original = path.read_text(encoding="utf-8") if path.exists() else None
        path.write_text(new_content, encoding="utf-8")
        ok, detail = bean_check(main_path)
        if not ok:
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(original, encoding="utf-8")
            result["error_msg"] = f"bean-check failed: {detail}"
            return result
        rel = path.relative_to(root.parent) if root.parent in path.parents else path.name
        result["git_commit_sha"] = git_commit_push(
            root, [str(rel)], f"[reconciliation] resolve {discrepancy_id}: {action}")
        result["success"] = True
        return result


# ── Anotación de una diferencia aprobada → tx al ledger (Story 6.3, modelo A) ──


def annotate_discrepancy(
    discrepancy: dict,
    *,
    category_account: str | None,
    importer,
    ledger_root,
    ts: str,
) -> dict:
    """Anota una diferencia `missing-in-laudus` aprobada: renderiza la tx de la cartola y la escribe
    a la zona `manual/` (Story 6.3, modelo A — cierra el lazo "aprobar → contabilizar").

    Append puro (la línea existe en la cartola, no en Laudus → es un gasto real que falta), por eso
    NO toca `imports/laudus/*`. Escribe a `manual/reconciliation-<cuenta>-<YYYY-MM>.beancount` (incluido
    por `main.beancount`), vía `commit_reconciliation` (write-and-replace + bean-check + rollback + git).

    Categoría (decisión Ary Q2): si el contador no fija una cuenta destino → `Suspense` + `category_status
    "pending"` (lo levanta `/categorizacion` 9.7); si fija una `Expenses:...` real → `confirmed`.

    Devuelve el mismo shape que `commit_reconciliation`: `{success, git_commit_sha, error_msg, file, ...}`.
    """
    from datetime import date as _date
    from pathlib import Path

    from beancount.core import data

    from pipeline.importers.bank_account_resolver import UnknownBankAccount
    from pipeline.importers.category_predictor import SUSPENSE_ACCOUNT
    from pipeline.importers.cartola_pdf_importer import (
        _LIABILITY_ROOT, _build_postings, build_usd_postings, render_entries,
    )

    root = Path(ledger_root)
    disc_id = discrepancy.get("discrepancy_id")
    cartola = discrepancy.get("cartola") or {}
    bank_account_id = discrepancy.get("bank_account_id")

    fail = {"discrepancy_id": disc_id, "action": "confirm-cartola-only", "file": None,
            "success": False, "error_msg": None, "git_commit_sha": None}
    if not cartola or cartola.get("amount") is None or not cartola.get("date"):
        fail["error_msg"] = "la discrepancia no tiene datos de cartola para anotar"
        return fail

    try:  # fail-closed: id desconocido/None → 422 limpio (AC2), no 500 con la discrepancia abierta
        account_target = importer.resolver.resolve(bank_account_id)
    except UnknownBankAccount as exc:
        fail["error_msg"] = f"no se puede anotar: {exc}"
        return fail
    is_liability = account_target.startswith(_LIABILITY_ROOT)
    category = category_account or SUSPENSE_ACCOUNT
    is_suspense = category == SUSPENSE_ACCOUNT

    amount = Decimal(str(cartola["amount"]))  # el JSONL guardó float vía _num → castear a Decimal
    currency = cartola.get("currency") or "CLP"
    when = _date.fromisoformat(cartola["date"])
    line_no = cartola.get("line_no")

    meta_extra: dict = {}
    if currency != "CLP":
        if currency != "USD":  # fail-closed: build_usd_postings hardcodea USD/CLP → no rutear EUR etc.
            fail["error_msg"] = f"moneda {currency!r} no soportada para anotar (sólo CLP/USD)"
            return fail
        fx_implied = (discrepancy.get("fx") or {}).get("implied")
        if fx_implied is None or Decimal(str(fx_implied)) <= 0:
            fail["error_msg"] = "no se puede anotar la línea USD: FX ausente o no-positivo (BCCh)"
            return fail
        fx_implied = Decimal(str(fx_implied))
        postings = build_usd_postings(account_target, category, amount, fx_implied, is_liability)
        meta_extra["fx_implied"] = str(fx_implied)
    else:
        postings = _build_postings(account_target, category, amount, currency, is_liability)

    bmeta = data.new_metadata("<reconcile-annotate>", line_no or 0)
    bmeta.update({
        "source": "reconciliation",
        "bank_account_id": bank_account_id,
        "ref_discrepancy_id": disc_id,
        "line": str(line_no),
        "match_source": "pending" if is_suspense else "reconciliation",
        # Suspense → pending (lo levanta /categorizacion); categoría real → confirmed.
        "category_status": "pending" if is_suspense else "confirmed",
    })
    bmeta.update(meta_extra)
    entry = data.Transaction(
        meta=bmeta, date=when, flag="!" if is_suspense else "*", payee=None,
        narration=cartola.get("description") or f"line {line_no}",
        tags=frozenset(), links=frozenset(), postings=postings,
    )

    acct_leaf = account_target.rsplit(":", 1)[-1]
    out_dir = root / "manual"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"reconciliation-{acct_leaf}-{when.strftime('%Y-%m')}.beancount"
    existing = out_file.read_text(encoding="utf-8") if out_file.exists() else ""
    new_content = existing + render_entries([entry])
    return commit_reconciliation(out_file, new_content, disc_id, "confirm-cartola-only", root)


# ── Conciliación en el promote: el SEAM del upload (Story 6.1, modelo A) ──────


def _discrepancies_path(ledger_root):
    """Ruta del JSONL de discrepancias — misma resolución que el dashboard 9.12
    (`reconciliation.service._jsonl_path`): `LEDGER_DISCREPANCIES` override → si no,
    `<ledger_root>/_meta/cartola-discrepancies.jsonl`. Se replica acá (en vez de importar
    la capa API) para no invertir la dependencia pipeline→backend."""
    from pathlib import Path

    override = os.getenv("LEDGER_DISCREPANCIES")
    if override:
        return Path(override)
    return Path(ledger_root) / "_meta" / "cartola-discrepancies.jsonl"


def _runs_path(ledger_root):
    """Ruta del JSONL de run-records (Story 6.5) — espejo de `_discrepancies_path` y de
    `reconciliation.service._runs_path`: override `LEDGER_RECONCILIATION_RUNS` → si no,
    `<ledger_root>/_meta/reconciliation-runs.jsonl`."""
    from pathlib import Path

    override = os.getenv("LEDGER_RECONCILIATION_RUNS")
    if override:
        return Path(override)
    return Path(ledger_root) / "_meta" / "reconciliation-runs.jsonl"


def reconcile_cartola(batch_id: str, importer, ledger_root, *, ts: str) -> dict:
    """Concilia una cartola staged contra Laudus y registra las DIFERENCIAS (Story 6.1, modelo A).

    **No postea nada al ledger.** Laudus (`imports/laudus/*`) sigue siendo la fuente contabilizada y
    validada peso-por-peso vs el contador; la cartola es la lupa que detecta diferencias. Postear las
    líneas de cartola encima duplicaría las cuentas de banco/TC (Laudus ya las tiene) y rompería el
    cuadre. La anotación en Beancount de una diferencia *aprobada* vive en el flujo de resolución del
    dashboard (próxima story), no acá.

    Flujo:
    1. Arma `CartolaLine[]` desde el canónico staged + carga `load_laudus_entries()` del período.
    2. Corre el matching (`reconcile_and_build`) y queda con las discrepancias (las entries que
       construye se DESCARTAN — no se contabilizan).
    3. Appendea todas las discrepancias al JSONL (dedup) y commitea el JSONL (gateado por
       `IMPORTER_GIT_ENABLED`) para que sobrevivan al `git reset --hard` del refresh del backend.
    4. Consume el staging y devuelve el resumen: total de diferencias + cuántas son bloqueantes.

    `perfect` no genera diferencia (la cartola coincide con Laudus, nada que revisar).
    """
    from pathlib import Path

    from bootstrap.account_mapping import slugify
    from backend.app.integrations.cartola_schema import CartolaCanonicalV1
    from pipeline.importers.cartola_pdf_importer import _LIABILITY_ROOT
    from pipeline.importers.category_predictor import SUSPENSE_ACCOUNT
    from pipeline.importers.discrepancy_writer import append_discrepancies, append_run, build_run
    from pipeline.importers.laudus_run import acquire_lock, git_commit_push
    from pipeline.importers.matching_engine import load_laudus_entries

    root = Path(ledger_root)
    staging = root / "imports" / "cartolas" / "_staging" / f"{batch_id}.cartola.json"
    lock_path = root / ".import.lock"
    laudus_dir = root / "imports" / "laudus"
    fx_path = root / "_meta" / "fx-bcch-eom.jsonl"
    disc_path = _discrepancies_path(root)
    runs_path = _runs_path(root)

    model = CartolaCanonicalV1.model_validate_json(staging.read_text(encoding="utf-8"))
    bank_account_id = model.source.bank_account_id
    account_target = importer.resolver.resolve(bank_account_id)
    is_liability = account_target.startswith(_LIABILITY_ROOT)
    bank_slug = slugify(model.source.bank_name) or "Banco"
    year_month = model.period.end.strftime("%Y-%m")

    result = {"batch_id": batch_id, "status": "reconciled", "matched": 0,
              "differences": 0, "blocking": 0, "new": 0, "git_commit_sha": None}

    def _rel(p: Path) -> str:
        return str(p.relative_to(root.parent)) if root.parent in p.parents else p.name

    with acquire_lock(lock_path):
        cartola_lines = [
            CartolaLine(line_no=tx.line_no, date=tx.date, amount=tx.amount,
                        currency=tx.currency, description=tx.description, suggested_category="")
            for tx in model.transactions
        ]
        # Story 6.5b: la ventana de carga se padea ±DATE_TOLERANCE_DAYS para que la tolerancia de
        # fecha del matcher (±3d) alcance asientos Laudus fechados 1-2d fuera del período (value-date
        # vs fecha del estado) → sin esto, la línea del borde quedaba `missing-in-laudus` falso. El
        # padding solo es para MATCHEAR; `missing-in-cartola` se acota al período core más abajo.
        tol = timedelta(days=DATE_TOLERANCE_DAYS)
        laudus_entries = load_laudus_entries(
            laudus_dir, account_target, model.period.start - tol, model.period.end + tol)

        # reconcile_and_build hace el matching + arma discrepancias (mismas reglas/estados/FX que el
        # dashboard ya consume). Las entries beancount que produce se descartan (modelo A: no posteamos).
        _entries, discrepancies = reconcile_and_build(
            cartola_lines=cartola_lines, laudus_entries=laudus_entries,
            period_start=model.period.start, account_target=account_target, is_liability=is_liability,
            category_for=lambda cl: SUSPENSE_ACCOUNT, fx_jsonl_path=fx_path, bank_slug=bank_slug,
            year_month=year_month, batch_id=batch_id, bank_account_id=bank_account_id, ts=ts,
        )

        # Story 6.5b: el padding de la ventana puede traer asientos Laudus de estados ADYACENTES
        # (fuera del período core). Sin línea de cartola, el matcher los marca `missing-in-cartola`;
        # se descartan para no emitir diferencias falsas del mes vecino (el padding es solo para que
        # el match del borde alcance su contraparte, no para flaggear asientos de otros estados).
        core_start, core_end = model.period.start, model.period.end

        def _in_core(d: dict) -> bool:
            if d.get("state") != "missing-in-cartola":
                return True
            ld = (d.get("laudus") or {}).get("date")
            return not ld or core_start <= date.fromisoformat(str(ld)) <= core_end

        discrepancies = [d for d in discrepancies if _in_core(d)]

        # D5 (review 2026-07-06): batch con UNA lectura del JSONL — el loop de
        # append_discrepancy releía el archivo completo por cada discrepancia.
        new = append_discrepancies(discrepancies, disc_path)
        result["differences"] = len(discrepancies)
        result["new"] = new
        result["blocking"] = len([d for d in discrepancies if d.get("state") in _BLOCKING])
        # Líneas de cartola sin diferencia = total − líneas distintas que generaron ≥1 discrepancia.
        # Dedup por line_no: una línea puede emitir 2 discrepancias (soft-mismatch + FX) y no debe
        # restarse dos veces (matched quedaría subestimado / negativo).
        diff_lines = {ln for d in discrepancies
                      if (ln := (d.get("cartola") or {}).get("line_no")) is not None}
        result["matched"] = len(model.transactions) - len(diff_lines)

        # Story 6.5 AC1: dejar un run-record del período (sobrevive el git reset del refresh y
        # distingue 'cartola perfecta'/'todas resueltas' de 'nunca subida'). Append-only; el lector
        # (`list_periods`) toma el más reciente por (cuenta, mes).
        append_run(build_run(
            bank_account_id=bank_account_id, year_month=year_month, reconciled_at=ts,
            matched=result["matched"], differences=result["differences"],
            blocking=result["blocking"], batch_id=batch_id), runs_path)

        # Story 6.5 AC2: el run-record se commitea SIEMPRE (incluso cartola perfecta con new==0), si
        # no el `git reset --hard` del refresh lo perdería. El JSONL de discrepancias se incluye solo
        # si hubo nuevas (semántica de 6.1). `git_commit_push` es no-op idempotente sin git habilitado.
        commit_paths = [_rel(runs_path)] + ([_rel(disc_path)] if new else [])
        result["git_commit_sha"] = git_commit_push(
            root, commit_paths,
            f"[reconcile-cartola] {bank_slug} {year_month}: {len(discrepancies)} diferencia(s) + run")

        # El canónico ya se consumió (extraído + reconciliado); el staging se limpia.
        staging.unlink(missing_ok=True)
        return result
