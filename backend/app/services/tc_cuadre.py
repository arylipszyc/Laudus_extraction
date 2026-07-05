"""Cuadre de una cartola TC contra la contabilidad (beancount) — C1–C5 (Story 6.6, diseño Valentina).

La v1 (88d1828) dejó C1 + el chequeo de pago, inline al postear. Esta versión computa los CINCO
chequeos del spec (`valentina-bug-categorizacion-destruye-tc-real-2026-07-02.md` §"Chequeos de cuadre"):

- **C1** (🔴) `saldo TC:Real al cierre == −closing` (USD: `−closing×fx`) — deuda mal materializada.
  Este es el que habría cachado el bug de categorización desde la primera cartola.
- **C2** (🟡) `apertura[M] == cierre[M−1]` — contigüidad, misma tarjeta, moneda nativa.
- **C3** (🔴) integridad del asiento: toda compra/cuota tiene UNA pata `TC:Real` y las 2 patas difieren.
- **C4** (🟡) `pago de la cartola == pago que registró Laudus` (se expone como `pago_ok`, como la v1).
- **C5** (🟡) el lump `Expenses:EAG:TC:<stem>-<code>` del mes quedó neteado (≈0).

`opening`/`closing`/`currency`/`fx` se leen de la metadata persistida en los asientos (Story 6.6, Task 1),
con fallback al `closing` explícito del request (el path inline de `validate-balance` lo tiene ahí).
Función PURA (recibe las `entries` del ledger); la usan el router de cartolas y `GET /tc/reconciliation`.
"""
from __future__ import annotations

from decimal import Decimal

from beancount.core import data

_TOL_CLP = Decimal("1")     # CLP: sin decimales
_TOL_USD = Decimal("0.01")
_TC_REAL_PREFIX = "Liabilities:EAG:TC:Real:"
_CONSUMO_OPS = {"compra", "cuota"}  # las que deben tener pata TC:Real (C3)


def _month(d) -> str:
    return d.isoformat()[:7]


def _prev_month(year_month: str) -> str:
    """`"2026-01"` → `"2025-12"`; `"2026-04"` → `"2026-03"`."""
    y, m = int(year_month[:4]), int(year_month[5:7])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _native_tol(currency: str) -> Decimal:
    return _TOL_USD if (currency or "CLP") != "CLP" else _TOL_CLP


def _statement_meta(entries: list, tc_real_account: str, year_month: str) -> dict | None:
    """opening/closing/fx/currency de la cartola `year_month` de esta tarjeta, desde la metadata
    persistida (Story 6.6). `None` si no hay asientos de esa cartola en el ledger.

    Busca el primer asiento `source=cartola-tc` con `period == year_month` que toca `tc_real_account`
    y trae `opening`/`closing` en la meta. Todos los asientos del batch llevan los mismos valores.
    """
    for e in entries:
        if not isinstance(e, data.Transaction):
            continue
        meta = e.meta or {}
        if meta.get("source") != "cartola-tc" or meta.get("period") != year_month:
            continue
        if "opening" not in meta or "closing" not in meta:
            continue
        if not any(p.account == tc_real_account for p in e.postings):
            continue
        return {
            "opening": Decimal(str(meta["opening"])),
            "closing": Decimal(str(meta["closing"])),
            "fx": Decimal(str(meta["fx"])) if meta.get("fx") else Decimal(1),
            "currency": meta.get("currency") or "CLP",
        }
    return None


def compute_tc_cuadre(
    entries: list,
    *,
    tc_real_account: str,
    lump_account: str,
    year_month: str,
    closing: Decimal | None = None,
    bank_account_id: str | None = None,
) -> dict:
    """Cuadre C1–C5 de la cartola `year_month` de una tarjeta contra el ledger `entries`.

    `tc_real_account` = `Liabilities:EAG:TC:Real:<stem>`; `lump_account` = la cuenta de gasto que
    Laudus usa para el pago (`Expenses:EAG:TC:<stem>-<code>`). `closing` (opcional): cierre declarado
    por la cartola en moneda nativa — si se omite, se lee de la metadata persistida. `bank_account_id`
    (opcional): scope de C3; si se pasa, C3 evalúa las compras/cuotas de ESA tarjeta (detecta la pata
    `TC:Real` destruida aunque ya no toque la cuenta); si no, C3 scopea por la cuenta.
    """
    stmt = _statement_meta(entries, tc_real_account, year_month)
    fx = stmt["fx"] if stmt else Decimal(1)
    currency = stmt["currency"] if stmt else "CLP"
    opening = stmt["opening"] if stmt else None
    if closing is None:
        closing = stmt["closing"] if stmt else Decimal(0)
    else:
        closing = Decimal(str(closing))

    # ── C1 — saldo TC:Real acumulado hasta el fin del mes de la cartola vs −(closing×fx) ──
    # TC:Real se postea en CLP (montos × fx del estado). El saldo acumulado en CLP **telescopa** a
    # −closing×fx_del_estado de forma exacta: el pago (b) de cada mes es el CLP REAL que canceló las
    # compras del mes anterior (mismo CLP), así que se anulan y solo sobrevive −closing_M×fx_M. Por eso
    # C1 compara en CLP contra −(closing×fx), con la apertura ya valorizada al CLP del pago que la salda
    # (fix en tc_correction). Verificado sobre 1027 USD feb/mar: diff 0,00. (Comparar en nativo dividiendo
    # por fx se rompe: el pago lleva CLP real al fx del mes ANTERIOR pero está estampado con el del mes
    # actual → mis-valora ~1 dólar por mes.) Tolerancia CLP.
    tc_real_balance = Decimal(0)
    for e in entries:
        if isinstance(e, data.Transaction) and _month(e.date) <= year_month:
            for p in e.postings:
                if p.account == tc_real_account and p.units:
                    tc_real_balance += p.units.number
    closing_clp = closing * fx
    c1_ok = abs(tc_real_balance + closing_clp) <= _TOL_CLP

    # ── C2 — contigüidad: apertura[M] == cierre[M−1] (misma tarjeta, moneda nativa) ──
    prev = _statement_meta(entries, tc_real_account, _prev_month(year_month))
    if prev is None or opening is None:
        c2_ok = False
        c2_reason = "sin cartola anterior" if prev is None else "sin apertura persistida"
        c2_prior_closing = None
    else:
        c2_prior_closing = prev["closing"]
        c2_ok = abs(opening - c2_prior_closing) <= _native_tol(currency)
        c2_reason = None

    # ── C3 — integridad del asiento: compra/cuota con UNA pata TC:Real y 2 cuentas distintas ──
    # Caza el bug de categorización (reescribía ambas patas a Expenses → pata de deuda destruida).
    c3_corrupted = 0
    for e in entries:
        if not isinstance(e, data.Transaction):
            continue
        meta = e.meta or {}
        if (meta.get("source") != "cartola-tc"
                or meta.get("period") != year_month
                or meta.get("operation_type") not in _CONSUMO_OPS):
            continue
        if bank_account_id is not None:
            if meta.get("bank_account_id") != bank_account_id:
                continue
        elif not any(p.account == tc_real_account for p in e.postings):
            continue
        real_legs = [p for p in e.postings if p.account.startswith(_TC_REAL_PREFIX)]
        if len(real_legs) != 1 or len({p.account for p in e.postings}) < 2:
            c3_corrupted += 1
    c3_ok = c3_corrupted == 0

    # ── C4 — pago de la cartola vs pago que registró Laudus (idéntico a la v1) ──
    pago_cartola = Decimal(0)
    for e in entries:
        if not isinstance(e, data.Transaction):
            continue
        meta = e.meta or {}
        if meta.get("source") == "cartola-tc" and meta.get("operation_type") == "pago" \
                and _month(e.date) == year_month:
            for p in e.postings:
                if p.account == tc_real_account and p.units:
                    pago_cartola += p.units.number

    laudus_payments: list[dict] = []
    for e in entries:
        if not isinstance(e, data.Transaction) or _month(e.date) != year_month:
            continue
        if (e.meta or {}).get("source") == "cartola-tc":
            continue
        lump_leg = next((p for p in e.postings if p.account == lump_account and p.units), None)
        if lump_leg is None or lump_leg.units.number <= 0:
            continue
        bank_leg = next((p for p in e.postings
                         if p.account.split(":")[0] == "Assets" and p.units), None)
        laudus_payments.append({
            "date": e.date.isoformat(),
            "narration": e.narration or "",
            "amount": float(lump_leg.units.number),
            "bank_account": bank_leg.account if bank_leg else None,
        })
    laudus_total = Decimal(str(sum(p["amount"] for p in laudus_payments)))
    pago_ok = bool(laudus_payments) and abs(pago_cartola - laudus_total) <= _TOL_CLP

    # ── C5 — lump residual: el gasto lumpeado del mes quedó neteado (≈0) tras la cartola ──
    lump_residual = Decimal(0)
    for e in entries:
        if isinstance(e, data.Transaction) and _month(e.date) == year_month:
            for p in e.postings:
                if p.account == lump_account and p.units:
                    lump_residual += p.units.number
    c5_ok = abs(lump_residual) <= _TOL_CLP

    # ── Semáforo agregado: rojo si C1 o C3; amarillo si algún 🟡; verde si todo pasa ──
    if not (c1_ok and c3_ok):
        status = "red"
    elif not (c2_ok and pago_ok and c5_ok):
        status = "yellow"
    else:
        status = "green"

    return {
        # C1
        "c1_ok": c1_ok,
        "tc_real_balance": float(tc_real_balance),
        "closing": float(closing),
        "closing_clp": float(closing_clp),
        "currency": currency,
        "fx": float(fx),
        "opening": float(opening) if opening is not None else None,
        # C2
        "c2_ok": c2_ok,
        "c2_prior_closing": float(c2_prior_closing) if c2_prior_closing is not None else None,
        "c2_reason": c2_reason,
        # C3
        "c3_ok": c3_ok,
        "c3_corrupted_count": c3_corrupted,
        # C4 (pago)
        "pago_cartola": float(pago_cartola),
        "laudus_payment_total": float(laudus_total),
        "laudus_payments": laudus_payments,
        "pago_ok": pago_ok,
        # C5
        "c5_ok": c5_ok,
        "c5_residual": float(lump_residual),
        # agregado
        "status": status,
    }
