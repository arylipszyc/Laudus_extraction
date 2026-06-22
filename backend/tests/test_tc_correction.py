"""Story 6.2 — corrección contable de TC vía cartola (backbone de asientos, flujo Valentina).

Cubre el builder puro `build_tc_correction_entries` para una cartola CLP (fx=1): asientos
(a) compra/cuota, abono (espejo), (b) pago, (c) apertura; bean-check real sobre el render; y la
prueba de no-doble-conteo (§7): el gasto neto = Σ compras − Σ abonos, y la cuenta-gasto Laudus
queda en 0 tras la reclasificación del pago.

USD/FX se cubre aparte (la derivación del FX desde Laudus es la pieza con matching, fuera de este
backbone — ver storyfile).
"""
from decimal import Decimal

from beancount import loader
from beancount.core import data

from datetime import date

from backend.app.integrations.cartola_schema import CartolaCanonicalV1
from pipeline.importers.cartola_pdf_importer import render_entries
from pipeline.importers.matching_engine import LaudusEntry
from pipeline.importers.tc_correction import (
    OPENING_EQUITY,
    build_tc_correction_entries,
    derive_statement_fx,
    parse_glosa_usd,
)

TC_REAL = "Liabilities:EAG:TC:Real:VisaTest"
EXP_TC = "Expenses:EAG:TC:TcTest-430099"
CAT = "Expenses:EAG:Super"

ACCOUNTS = f"""\
2020-12-31 open {TC_REAL} CLP
2020-12-31 open {EXP_TC} CLP
2020-12-31 open {CAT} CLP
2020-12-31 open {OPENING_EQUITY} CLP
2020-12-31 open Assets:EAG:Bancos:Test CLP
"""


def _model(txs, *, opening="0", closing=None, currency="CLP", start="2026-03-01", end="2026-03-31"):
    """txs = list of (date, desc, amount_int, operation_type)."""
    if closing is None:
        closing = str(int(opening) + sum(a for _, _, a, _ in txs))
    payload = {
        "schema_version": "1.0",
        "source": {"bank_account_id": "tc-test", "bank_name": "Banco Test",
                   "account_label": "Visa Test 1234", "account_type": "tarjeta_credito", "entity": "EAG"},
        "period": {"start": start, "end": end},
        "currency": currency,
        "balances": {"opening": opening, "closing": closing},
        "transactions": [
            {"line_no": i + 1, "date": d, "description": desc, "amount": str(a),
             "currency": currency, "raw": {"operation_type": op}}
            for i, (d, desc, a, op) in enumerate(txs)
        ],
        "extraction": {"model": "test", "extracted_at": "2026-04-01T00:00:00Z", "warnings": []},
    }
    return CartolaCanonicalV1.model_validate(payload)


def _build(model, *, emit_opening=False):
    return build_tc_correction_entries(
        model=model, tc_real_account=TC_REAL, expense_tc_account=EXP_TC, fx=Decimal(1),
        lump_for=lambda tx: abs(tx.amount), category_for=lambda tx: CAT,
        batch_id="b1", bank_account_id="tc-test", emit_opening=emit_opening,
    )


def _net_by_account(entries):
    net = {}
    for e in entries:
        for p in e.postings:
            net[p.account] = net.get(p.account, Decimal(0)) + p.units.number
    return net


def _bean_check(tmp_path, entries, extra=""):
    (tmp_path / "accounts.beancount").write_text(ACCOUNTS, encoding="utf-8")
    (tmp_path / "entries.beancount").write_text(render_entries(entries), encoding="utf-8")
    if extra:
        (tmp_path / "extra.beancount").write_text(extra, encoding="utf-8")
    main = 'include "accounts.beancount"\ninclude "entries.beancount"\n'
    if extra:
        main += 'include "extra.beancount"\n'
    (tmp_path / "main.beancount").write_text(main, encoding="utf-8")
    _e, errors, _o = loader.load_file(str(tmp_path / "main.beancount"))
    return errors


# ── (a) compra → deuda sube, gasto sube ───────────────────────────────────────


def test_compra_genera_asiento_a(tmp_path):
    m = _model([("2026-03-10", "JUMBO", 45000, "compra")])
    entries = _build(m)
    net = _net_by_account(entries)
    assert net[TC_REAL] == Decimal("-45000.00")   # ↑ deuda (liability negativa)
    assert net[CAT] == Decimal("45000.00")         # ↑ gasto
    assert _bean_check(tmp_path, entries) == []


# ── abono → espejo invertido de la compra (amount negativo) ───────────────────


def test_abono_invierte_el_asiento(tmp_path):
    m = _model([("2026-03-12", "DEVOLUCION", -21480, "abono")])
    net = _net_by_account(_build(m))
    assert net[TC_REAL] == Decimal("21480.00")     # ↓ deuda
    assert net[CAT] == Decimal("-21480.00")        # ↓ gasto (revierte)


# ── (b) pago → saca el gasto falso de la cuenta-gasto Laudus, baja la deuda ────


def test_pago_reclasifica_sin_tocar_banco(tmp_path):
    m = _model([("2026-03-20", "MONTO CANCELADO", -100000, "pago")])
    entries = _build(m)
    net = _net_by_account(entries)
    assert net[EXP_TC] == Decimal("-100000.00")    # saca el lump-gasto de Laudus
    assert net[TC_REAL] == Decimal("100000.00")    # ↓ deuda real
    assert "Assets:EAG:Bancos:Test" not in net     # NO toca el banco
    assert _bean_check(tmp_path, entries) == []


# ── (c) apertura → Equity, una sola vez, NO gasto ─────────────────────────────


def test_apertura_va_a_equity(tmp_path):
    m = _model([("2026-03-10", "JUMBO", 45000, "compra")], opening="500000")
    net = _net_by_account(_build(m, emit_opening=True))
    assert net[TC_REAL] == Decimal("-545000.00")   # -500k apertura + -45k compra
    assert net[OPENING_EQUITY] == Decimal("500000.00")
    assert CAT in net and net[CAT] == Decimal("45000.00")  # la apertura NO infla el gasto


def test_apertura_no_se_emite_si_emit_opening_false(tmp_path):
    m = _model([("2026-03-10", "JUMBO", 45000, "compra")], opening="500000")
    net = _net_by_account(_build(m, emit_opening=False))
    assert OPENING_EQUITY not in net


# ── No doble conteo (§7): gasto neto = Σ compras − Σ abonos; Expenses:TC → 0 ───


def test_no_doble_conteo_suma_anual(tmp_path):
    # Laudus ya puso el pago como gasto en la cuenta-gasto TC (+100k). El asiento (b) lo saca.
    laudus_lump = (f'2026-03-20 * "Pago TC (Laudus)"\n'
                   f'  Assets:EAG:Bancos:Test  -100000.00 CLP\n'
                   f'  {EXP_TC}  100000.00 CLP\n')
    m = _model([
        ("2026-03-10", "JUMBO", 45000, "compra"),
        ("2026-03-12", "DEVOLUCION", -5000, "abono"),
        ("2026-03-20", "MONTO CANCELADO", -100000, "pago"),
    ])
    entries = _build(m)
    # bean-check sobre Laudus-lump + corrección juntos
    assert _bean_check(tmp_path, entries, extra=laudus_lump) == []
    # Gasto neto del período: Expenses:TC vuelve a 0, gasto real = compras − abonos = 40.000
    import beancount.loader as bl
    bl_entries, _err, _opt = bl.load_file(str(tmp_path / "main.beancount"))
    from beancount.core import inventory
    bal_exp_tc = inventory.Inventory()
    bal_cat = inventory.Inventory()
    for e in bl_entries:
        if isinstance(e, data.Transaction):
            for p in e.postings:
                if p.account == EXP_TC:
                    bal_exp_tc.add_amount(p.units)
                elif p.account == CAT:
                    bal_cat.add_amount(p.units)
    assert bal_exp_tc.get_currency_units("CLP").number == Decimal("0")        # lump neteado
    assert bal_cat.get_currency_units("CLP").number == Decimal("40000.00")     # 45k − 5k


# ── FX USD: glosa del pago Laudus ─────────────────────────────────────────────


def test_parse_glosa_usd():
    assert parse_glosa_usd("USD26.188,93 Visa BCI 1027 Abril") == Decimal("26188.93")
    assert parse_glosa_usd("USD838,48 Visa BCI 1027 Diciembre") == Decimal("838.48")
    assert parse_glosa_usd("USD1.448,79 Visa BCI 1027 Enero") == Decimal("1448.79")
    assert parse_glosa_usd("Pago en pesos sin USD") is None


def _us_payment(d, clp, glosa):
    return LaudusEntry(je_id="x", date=d, amount=Decimal(clp), description=glosa,
                       category_account="Assets:EAG:Bancos:BancoBci10160175-111005")


# datos reales: estado 28/03→28/04 closing USD26.188,93, pagado 14/05 con 23.543.848 CLP.


def test_derive_fx_desde_glosa_real(tmp_path):
    m = _model([("2026-04-10", "EBAY", 100, "compra")], opening="0", closing="26188.93",
               currency="USD", start="2026-03-28", end="2026-04-28")
    us = [_us_payment(date(2026, 5, 14), "23543848.00", "USD26.188,93 Visa BCI 1027 Abril")]
    res = derive_statement_fx(m, us)
    assert res["status"] == "ok"
    assert res["lump_clp"] == Decimal("23543848.00")
    assert res["glosa_usd"] == Decimal("26188.93")
    # 23543848 / 26188.93 ≈ 898.99 CLP/USD
    assert Decimal("898") < res["fx"] < Decimal("900")


def test_derive_fx_bloqueante_si_no_hay_pago_que_cuadre(tmp_path):
    # El pago que existe tiene OTRO USD (no salda este estado) → falta movimiento / error.
    m = _model([("2026-04-10", "EBAY", 100, "compra")], opening="0", closing="26188.93",
               currency="USD", start="2026-03-28", end="2026-04-28")
    us = [_us_payment(date(2026, 5, 14), "9994897.00", "USD10.843,04 Visa BCI 1027 Mayo")]
    res = derive_statement_fx(m, us)
    assert res["status"] == "blocked" and res["fx"] is None


def test_derive_fx_bloqueante_si_pago_fuera_de_ventana(tmp_path):
    m = _model([("2026-04-10", "EBAY", 100, "compra")], opening="0", closing="26188.93",
               currency="USD", start="2026-03-28", end="2026-04-28")
    # pago con el USD correcto pero 6 meses después → fuera de ventana
    us = [_us_payment(date(2026, 11, 14), "23543848.00", "USD26.188,93 Visa BCI 1027 Abril")]
    res = derive_statement_fx(m, us)
    assert res["status"] == "blocked"
