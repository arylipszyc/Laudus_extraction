"""Parity check del balance-sheet: Sheets `balance_sheet_{entity}` vs Beancount — Story 9.15 AC1.

Compara, por (entity, cuenta), la posición neta que el dashboard Activos/Pasivos usaría desde
cada fuente, **AT un cierre de mes** (point-in-time):
- Sheets: `repo.get_records("balance_sheet_{entity}")` (snapshot vigente, source of truth hasta ahora).
- Beancount: `balance_sheet_via_beancount(ledger, entity, date_to=eom)` (lo que el dashboard leerá
  con `USE_BEANCOUNT_ENGINE_BALANCE_SHEET` on).

Net por cuenta = `debit_balance - credit_balance` (igual que el frontend `useBalanceSheet`).

Semántica de fecha (ver Dev Notes de la story): se compara **AT fin-de-mes**, NUNCA sobre un
rango multi-snapshot. El Sheets balance es un único snapshot vigente (`replace_sheet`), así que
el `--as-of` por defecto es el `query_date` más reciente de la hoja de cada entity.

Diffs clasificados:
- **TC / pasivo reclasificado** (la cuenta es `Liabilities:...` en Beancount): diff ESPERADO
  (modelado correcto vs Sheets viejo, architecture-c4 §2.5) — NO blocker.
- **resto:** se investiga; la story NO procede al flip hasta explicarlos.

Uso:
    GOOGLE_APPLICATION_CREDENTIALS=/ruta/sa.json GOOGLE_SHEET_ID=... \\
    LEDGER_PATH=ledger/main.beancount PYTHONUTF8=1 \\
    python scripts/parity_check_balance_sheet.py [--as-of 2026-05-31] [--entities EAG,Jocelyn,...]

Exit 0 = paridad (sólo diffs esperados); 1 = hay diffs inesperados; 2 = error de carga.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

from backend.app.api.v1.reportes.report_builder import _num

DEFAULT_ENTITIES = ["EAG", "Jocelyn", "Jeannette", "Johanna", "Jael"]

# Un balance-sheet solo lleva Activos/Pasivos/Patrimonio. La pestaña legacy de Sheets mete además
# cuentas de resultado (Income/Expenses, acumuladas en miles de millones) que el
# `balance_sheet_via_beancount` excluye a propósito → comparar todo genera ~140 diffs falsos
# (P&L) que tapan los reales. Se compara solo el universo del balance.
BALANCE_ROOTS = {"Assets", "Liabilities", "Equity"}


def _net(row: dict) -> float:
    """Posición neta de una fila de balance: debit_balance - credit_balance (= frontend)."""
    return _num(row.get("debit_balance")) - _num(row.get("credit_balance"))


def _snapshot_rows(rows: list[dict], snapshot: str) -> list[dict]:
    """Filas del snapshot AT fin-de-mes. La hoja `balance_sheet_{entity}` es multi-snapshot
    (upsert pk=account_id+query_date); sin filtrar, `aggregate_balance` sumaría N meses e
    inflaría el neto vs el point-in-time de Beancount. Si la hoja es plana (sin `query_date`)
    se devuelve tal cual."""
    if not any(r.get("query_date") for r in rows):
        return rows  # hoja plana sin dimensión de snapshot
    if not snapshot:
        return rows
    return [r for r in rows if str(r.get("query_date", ""))[:10] == snapshot]


def aggregate_balance(rows: list[dict]) -> dict[str, float]:
    """{account_number: net} sumando las filas (una por cuenta AT el snapshot)."""
    agg: dict[str, float] = defaultdict(float)
    for r in rows:
        agg[str(r.get("account_number", ""))] += _net(r)
    return agg


def balance_only(agg: dict[str, float], account_roots: dict[str, str]) -> dict[str, float]:
    """Filtra a las cuentas del balance (raíz ∈ Assets|Liabilities|Equity). Descarta las de
    resultado (Income/Expenses) que el tab legacy de Sheets incluye pero un balance-sheet no."""
    return {a: v for a, v in agg.items() if account_roots.get(a, "") in BALANCE_ROOTS}


def compare(sheets: dict[str, float], beancount: dict[str, float], tol: float = 0.5) -> list[dict]:
    """Diffs por cuenta donde |beancount - sheets| > tol (≈ 0 CLP, redondeo)."""
    out = []
    for acc in set(sheets) | set(beancount):
        s, b = sheets.get(acc, 0.0), beancount.get(acc, 0.0)
        if abs(b - s) > tol:
            out.append({"account": acc, "sheets": round(s), "beancount": round(b), "diff": round(b - s)})
    out.sort(key=lambda d: abs(d["diff"]), reverse=True)
    return out


def classify(diffs: list[dict], account_roots: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """Parte los diffs en (esperados, inesperados).

    Esperado = la cuenta es `Liabilities` en Beancount (reclasificación de TC/pasivo).
    `account_roots`: {account_number: raíz Beancount (Assets|Liabilities|Equity|...)}.
    """
    expected, unexpected = [], []
    for d in diffs:
        root = account_roots.get(d["account"], "")
        (expected if root == "Liabilities" else unexpected).append({**d, "root": root})
    return expected, unexpected


def _account_roots(ledger) -> dict[str, str]:
    """{code: raíz Beancount} desde los `open` (para clasificar diffs de TC/pasivo)."""
    from beancount.core.data import Open
    roots: dict[str, str] = {}
    for e in ledger.entries():
        if isinstance(e, Open):
            code = (e.meta or {}).get("code")
            if code is not None:
                roots[str(code)] = e.account.split(":")[0]
    return roots


def _load(entity: str, as_of: str | None):
    """Carga (sheets_rows, bean_rows, account_roots, as_of) para una entity. Separado para testear."""
    from backend.app.dependencies import get_repository
    from backend.app.services.bql_queries import balance_sheet_via_beancount
    from backend.app.services.ledger_service import LedgerService

    sheets_rows = get_repository().get_records(f"balance_sheet_{entity.lower()}")
    snapshot = as_of or max((str(r.get("query_date", ""))[:10] for r in sheets_rows if r.get("query_date")),
                            default="")
    # AT fin-de-mes: solo el snapshot del cierre, NUNCA sumar múltiples (ver docstring del módulo).
    sheets_rows = _snapshot_rows(sheets_rows, snapshot)
    ledger = LedgerService(os.getenv("LEDGER_PATH") or "ledger/main.beancount")
    bean = balance_sheet_via_beancount(ledger, entity, date_to=snapshot or None)
    return sheets_rows, bean["data"], _account_roots(ledger), snapshot


def _print_entity(entity: str, snapshot: str, expected: list[dict], unexpected: list[dict], n: int) -> None:
    print(f"\n── {entity} — balance AT {snapshot or '(latest)'} — {n} cuentas comparadas ──")
    if not expected and not unexpected:
        print("  ✅ 0 diferencias.")
        return
    if expected:
        print(f"  ℹ️  {len(expected)} diff(s) ESPERADO(s) — TC/pasivo reclasificado a Liabilities:")
        for d in expected[:20]:
            print(f"     {d['account']:<12} sheets={d['sheets']:>14,} bean={d['beancount']:>14,} diff={d['diff']:>14,}")
    if unexpected:
        print(f"  ❌ {len(unexpected)} diff(s) INESPERADO(s) — investigar antes de flipear:")
        print(f"     {'cuenta':<12} {'raíz':<12} {'sheets':>14} {'beancount':>14} {'diff':>14}")
        for d in unexpected[:30]:
            print(f"     {d['account']:<12} {d['root']:<12} {d['sheets']:>14,} {d['beancount']:>14,} {d['diff']:>14,}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--as-of", dest="as_of", default=None,
                    help="cierre de mes YYYY-MM-DD (default: query_date más reciente de la hoja)")
    ap.add_argument("--entities", default=",".join(DEFAULT_ENTITIES),
                    help="lista separada por comas (default: las 5)")
    args = ap.parse_args()
    entities = [e.strip() for e in args.entities.split(",") if e.strip()]
    if not entities:
        print("Error: no se especificaron entidades (--entities vacío).", file=sys.stderr)
        return 2

    total_unexpected = 0
    total_compared = 0
    for entity in entities:
        try:
            sheets_rows, bean_rows, roots, snapshot = _load(entity, args.as_of)
        except Exception as exc:  # noqa: BLE001 — script CLI: reportar y salir
            print(f"Error cargando {entity}: {exc}", file=sys.stderr)
            return 2
        # Sin tab en Sheets (o vacío) → no hay baseline contra qué comparar; se omite en vez de
        # marcar todas las cuentas de beancount como diff. En el modelo consolidado (EAG incluye a
        # las hijas) las entidades hijas no tienen tab propio y caen acá.
        if not sheets_rows:
            print(f"\n── {entity} — sin data en Sheets (tab inexistente o vacío) — se omite")
            continue
        agg_s = balance_only(aggregate_balance(sheets_rows), roots)
        agg_b = balance_only(aggregate_balance(bean_rows), roots)
        diffs = compare(agg_s, agg_b)
        expected, unexpected = classify(diffs, roots)
        _print_entity(entity, snapshot, expected, unexpected, len(set(agg_s) | set(agg_b)))
        total_unexpected += len(unexpected)
        total_compared += len(set(agg_s) | set(agg_b))

    print(f"\n{'='*60}")
    # Fail-safe: cero cuentas comparadas = no se pudo verificar paridad (creds vacías, hoja/entity
    # inexistente, ledger sin data). NO es un GO — un gate go/no-go no aprueba sin haber chequeado.
    if total_compared == 0:
        print("❌ No se comparó ninguna cuenta (¿creds/hoja/ledger vacíos?) — NO se puede verificar paridad.",
              file=sys.stderr)
        return 2
    if total_unexpected == 0:
        print("✅ Sólo diffs esperados (TC→Liabilities). Seguro flipear USE_BEANCOUNT_ENGINE_BALANCE_SHEET.")
        return 0
    print(f"❌ {total_unexpected} diff(s) inesperado(s) en total — NO flipear hasta investigar.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
