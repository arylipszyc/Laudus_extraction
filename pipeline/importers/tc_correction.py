"""Corrección contable de Tarjetas de Crédito vía cartola — Story 6.2 (flujo de Valentina).

NO toca Laudus. Emite asientos contables estándar al importar la cartola de una TC:

- (a) compra/cuota → `Liabilities:EAG:TC:Real:<x>` (−) / `Expenses:<categoría>` (+)
- abono           → mismo asiento (a) con `amount` firmado (negativo) → se invierte solo
- (b) pago        → `Expenses:EAG:TC:<code>` (−lump) / `Liabilities:EAG:TC:Real:<x>` (+lump)
                    (saca el "gasto" lumpeado que dejó Laudus; el lump CLP lo provee el caller)
- (c) apertura    → `Liabilities:EAG:TC:Real:<x>` (−opening) / `Equity:Apertura:TarjetasSinDetalle` (+)
                    una sola vez por tarjeta (primera cartola)

Para cartolas USD los montos se convierten a CLP con un FX único (`fx`, provisto por el caller —
derivado de la liquidación que salda el estado, ver Story 6.2). CLP nacional → `fx = 1`.

El builder es PURO: recibe `fx`, el lump por pago (`lump_for`) y la categoría (`category_for`) ya
resueltos. La derivación del FX/lump desde Laudus (matching de la liquidación) vive afuera.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Callable

from beancount.core import data
from beancount.core.amount import Amount

from backend.app.integrations.cartola_schema import CartolaCanonicalV1, CartolaTransaction

OPENING_EQUITY = "Equity:Apertura:TarjetasSinDetalle"
_CLP = "CLP"
_CENT = Decimal("0.01")

# Ventana (días tras el cierre del estado) para buscar el pago que lo salda en Laudus.
_FX_WINDOW_DAYS = 75
# El estado USD se considera "saldado por la glosa" si el USD de la glosa == closing del estado.
_USD_MATCH_TOLERANCE = Decimal("0.01")

# Glosa del pago Laudus, formato chileno: "USD26.188,93 Visa BCI 1027 Abril" → 26188.93.
_GLOSA_USD_RE = re.compile(r"USD\s*([\d.]*\d,\d{2})")


def parse_glosa_usd(text: str) -> Decimal | None:
    """Extrae el monto USD de la glosa del pago Laudus (formato chileno). None si no aparece."""
    m = _GLOSA_USD_RE.search(text or "")
    if not m:
        return None
    return Decimal(m.group(1).replace(".", "").replace(",", "."))


def derive_statement_fx(
    model: CartolaCanonicalV1,
    laudus_us_entries: list,
    *,
    window_days: int = _FX_WINDOW_DAYS,
) -> dict:
    """FX único del estado USD desde el pago de Laudus que lo salda (Story 6.2 §FX, regla Ary).

    Busca en `laudus_us_entries` (asientos de la cuenta `...Us`, de `load_laudus_entries`) el pago
    fechado tras el cierre del estado cuya **glosa codifica el mismo USD que el `closing`** del estado.
    `FX = CLP_del_pago / USD_de_la_glosa`. Valida el cuadre: si ningún pago matchea el USD del estado
    → bloqueante (falta un movimiento o hay un error en la extracción), NO se estima FX.

    Devuelve `{status, fx, lump_clp, glosa_usd, payment_date, reason}`. `status ∈ {ok, blocked}`.
    """
    total_usd = abs(model.balances.closing)
    end = model.period.end
    candidates = sorted(
        (le for le in laudus_us_entries if le.date >= end and (le.date - end).days <= window_days),
        key=lambda le: le.date,
    )
    for le in candidates:
        glosa = parse_glosa_usd(le.description)
        if glosa is not None and glosa != 0 and abs(glosa - total_usd) <= _USD_MATCH_TOLERANCE:
            return {"status": "ok", "fx": (le.amount / glosa), "lump_clp": le.amount,
                    "glosa_usd": glosa, "payment_date": le.date, "reason": None}
    return {"status": "blocked", "fx": None, "lump_clp": None, "glosa_usd": None, "payment_date": None,
            "reason": (f"sin pago Laudus que salde el estado (USD {total_usd}) en {window_days}d tras "
                       f"el cierre {end} — ¿falta un movimiento o el estado aún no se pagó?")}

# operation_types que son consumo/devolución (asiento a, signo según amount)
_PURCHASE_OPS = {"compra", "cuota", "abono"}
_PAYMENT_OPS = {"pago"}


def _posting(account: str, number: Decimal) -> data.Posting:
    return data.Posting(account, Amount(number, _CLP), None, None, None, None)


def _meta(*, line_no: int, bank_account_id: str, batch_id: str, op: str, fx: Decimal) -> dict:
    m = data.new_metadata("<tc-correction>", line_no)
    m.update({
        "source": "cartola-tc",
        "bank_account_id": bank_account_id,
        "batch_id": batch_id,
        "line": str(line_no),
        "operation_type": op,
    })
    if fx != Decimal(1):
        m["fx"] = str(fx)
    return m


def build_tc_correction_entries(
    *,
    model: CartolaCanonicalV1,
    tc_real_account: str,
    expense_tc_account: str,
    fx: Decimal,
    lump_for: Callable[[CartolaTransaction], Decimal],
    category_for: Callable[[CartolaTransaction], str],
    batch_id: str,
    bank_account_id: str,
    emit_opening: bool,
) -> list:
    """Asientos de corrección de una cartola de TC (flujo Valentina §6). Lista de `data.Transaction`.

    `fx`: CLP/unidad (1 para cartola CLP). `lump_for(tx)`: CLP del lump Laudus que reclasifica el
    pago `tx` (para CLP = magnitud de la línea; para USD = lump matcheado en Laudus). `category_for`:
    cuenta de gasto de una compra. `emit_opening`: True solo en la primera cartola de la tarjeta.
    """
    fx = Decimal(fx)
    entries: list = []

    for tx in model.transactions:
        op = (tx.raw or {}).get("operation_type") or ""
        if op in _PURCHASE_OPS:
            # (a) / abono: signed amount → abono (amount<0) invierte el asiento solo.
            clp = (tx.amount * fx).quantize(_CENT)
            if clp == 0:
                continue
            category = category_for(tx)
            postings = [_posting(tc_real_account, -clp), _posting(category, clp)]
        elif op in _PAYMENT_OPS:
            # (b) reclasificación del pago: saca el gasto falso de la cuenta-gasto Laudus.
            lump = Decimal(lump_for(tx)).quantize(_CENT)
            if lump == 0:
                continue
            postings = [_posting(expense_tc_account, -lump), _posting(tc_real_account, lump)]
        else:
            # operation_type desconocido → no se contabiliza acá (queda para revisión/discrepancia).
            continue
        entries.append(data.Transaction(
            meta=_meta(line_no=tx.line_no, bank_account_id=bank_account_id, batch_id=batch_id,
                       op=op, fx=fx),
            date=tx.date, flag="*", payee=None,
            narration=tx.description or f"line {tx.line_no}",
            tags=frozenset(), links=frozenset(), postings=postings,
        ))

    # (c) apertura — una sola vez por tarjeta. La deuda arrastrada va a Equity (no gasto).
    if emit_opening and model.balances.opening != 0:
        opening_clp = (model.balances.opening * fx).quantize(_CENT)
        meta = _meta(line_no=0, bank_account_id=bank_account_id, batch_id=batch_id, op="apertura", fx=fx)
        entries.append(data.Transaction(
            meta=meta, date=model.period.start, flag="*", payee=None,
            narration=f"Apertura TC {model.source.account_label}",
            tags=frozenset(), links=frozenset(),
            postings=[_posting(tc_real_account, -opening_clp), _posting(OPENING_EQUITY, opening_clp)],
        ))

    return entries
