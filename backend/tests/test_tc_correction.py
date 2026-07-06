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
    BANK_CHARGES_ACCOUNT,
    CAJA_CLP,
    CAJA_USD,
    OPENING_EQUITY,
    SUSPENSE_ACCOUNT,
    build_tc_correction_entries,
    correct_tc_cartola,
    derive_statement_fx,
    inherit_statement_fx,
    parse_glosa_usd,
    tc_real_account,
)
from pipeline.importers.tc_correction import _normalize_op

TC_REAL = "Liabilities:EAG:TC:Real:VisaTest"
EXP_TC = "Expenses:EAG:TC:TcTest-430099"
CAT = "Expenses:EAG:Super"

ACCOUNTS = f"""\
2020-12-31 open {TC_REAL} CLP
2020-12-31 open {EXP_TC} CLP
2020-12-31 open {CAT} CLP
2020-12-31 open {OPENING_EQUITY} CLP
2020-12-31 open Assets:EAG:Bancos:Test CLP
2020-12-31 open {BANK_CHARGES_ACCOUNT} CLP
2020-12-31 open {CAJA_CLP} CLP
2020-12-31 open {CAJA_USD} CLP
2020-12-31 open {SUSPENSE_ACCOUNT} CLP
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


def test_apertura_usd_al_fx_del_pago_que_la_salda(tmp_path):
    """Apertura USD: se valoriza al CLP real del pago (MONTO CANCELADO) que la salda, NO a
    opening×fx_del_estado → TC:Real cierra a −closing×fx sin diferencia de cambio fantasma
    (decisión Valentina 2026-07-04). Caso real 1027 USD feb: la deuda de enero se pagó a un fx
    distinto del estado de febrero."""
    fx = Decimal("931")
    # opening USD 1448.79 saldado por un MONTO CANCELADO cuyo CLP real (1.250.161, pagado a ~863)
    # ≠ opening×fx (1.348.823). + una compra de 465.62 USD.
    m = _model([("2026-02-10", "EBAY", 465.62, "compra"),
                ("2026-02-12", "MONTO CANCELADO", -1448.79, "pago")],
               opening="1448.79", closing="465.62", currency="USD",
               start="2026-02-01", end="2026-02-28")
    entries = build_tc_correction_entries(
        model=m, tc_real_account=TC_REAL, expense_tc_account=EXP_TC, fx=fx,
        lump_for=lambda tx: Decimal("1250161"), category_for=lambda tx: CAT,
        batch_id="b1", bank_account_id="tc-test", emit_opening=True,
    )
    net = _net_by_account(entries)
    assert net[OPENING_EQUITY] == Decimal("1250161")          # al pago real, NO 1448.79×931
    assert net[TC_REAL] == (-Decimal("465.62") * fx)          # cierra a −closing×fx (nativo exacto)
    assert net[EXP_TC] == Decimal("-1250161")                 # el pago sacó el gasto falso de Laudus
    assert _bean_check(tmp_path, entries) == []


def test_apertura_usd_fallback_si_no_se_salda_en_la_cartola(tmp_path):
    """Si ningún pago salda la apertura completa (opening parcial/en cuotas), cae al fx del estado
    (comportamiento previo) — no rompe, se acepta el residuo hasta que se salde."""
    fx = Decimal("931")
    m = _model([("2026-02-10", "EBAY", 465.62, "compra")],   # sin pago que matchee el opening
               opening="1448.79", closing="1914.41", currency="USD",
               start="2026-02-01", end="2026-02-28")
    entries = build_tc_correction_entries(
        model=m, tc_real_account=TC_REAL, expense_tc_account=EXP_TC, fx=fx,
        lump_for=lambda tx: abs(tx.amount), category_for=lambda tx: CAT,
        batch_id="b1", bank_account_id="tc-test", emit_opening=True,
    )
    net = _net_by_account(entries)
    assert net[OPENING_EQUITY] == (Decimal("1448.79") * fx)   # fallback opening×fx


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


# ── Mapeo COMPLETO de operation_type (§10.1 — cierra el drop silencioso) ──────


def test_normalize_op_robusto():
    # Sign-routing del vacío/None; sinónimos; case/espacios; no reconocido → "".
    assert _normalize_op(None, Decimal(100)) == "compra"
    assert _normalize_op(None, Decimal(-100)) == "abono"
    assert _normalize_op("", Decimal(50)) == "compra"
    assert _normalize_op("COMPRAS P.A.T.", Decimal(1)) == "compra"
    assert _normalize_op("  Pago ", Decimal(-1)) == "pago"      # case + espacios (sino crashea el USD)
    assert _normalize_op("nota_credito", Decimal(-1)) == "abono"
    assert _normalize_op("impuesto", Decimal(1)) == "impuesto"
    assert _normalize_op("xyz", Decimal(1)) == ""              # no reconocido → Suspense
    assert _normalize_op(5, Decimal(1)) == ""                  # op no-str (raw es Any) → no crashea


def test_none_positivo_normaliza_a_compra(tmp_path):
    m = _model([("2026-03-10", "UBER EATS", 12000, None)])
    net = _net_by_account(_build(m))
    assert net[TC_REAL] == Decimal("-12000.00")    # ↑ deuda
    assert net[CAT] == Decimal("12000.00")          # el signo + → compra categorizada
    assert _bean_check(tmp_path, _build(m)) == []


def test_none_negativo_normaliza_a_abono(tmp_path):
    m = _model([("2026-03-12", "REVERSO", -8000, None)])
    net = _net_by_account(_build(m))
    assert net[TC_REAL] == Decimal("8000.00")       # ↓ deuda (el signo − → abono)
    assert net[CAT] == Decimal("-8000.00")


def test_sinonimos_pat_y_cargo_son_compra(tmp_path):
    m = _model([("2026-03-10", "AGUAS ANDINAS", 30000, "COMPRAS P.A.T."),
                ("2026-03-11", "NETFLIX", 9000, "cargo_automatico")])
    net = _net_by_account(_build(m))
    assert net[CAT] == Decimal("39000.00")          # ambos sinónimos → compra
    assert net[TC_REAL] == Decimal("-39000.00")


def test_cargo_bancario_va_a_gastos_bancarios(tmp_path):
    # La fuga real de la BCI 2026-04: impuesto $781 + comisión $6.014 = $6.795 que se dropeaban.
    m = _model([("2026-03-10", "TIMBRE DL 3475", 781, "impuesto"),
                ("2026-03-10", "COBRO ADM MENSUAL", 6014, "comision")])
    entries = _build(m)
    net = _net_by_account(entries)
    assert net[BANK_CHARGES_ACCOUNT] == Decimal("6795.00")  # cuenta FIJA, no el categorizador 9.7
    assert net[TC_REAL] == Decimal("-6795.00")              # el pasivo ya no queda corto
    assert CAT not in net                                    # NO pasó por el 9.7
    assert _bean_check(tmp_path, entries) == []


def test_avance_va_a_caja_no_gasto(tmp_path):
    m = _model([("2026-03-10", "AVANCE EFECTIVO", 100000, "avance")])
    net = _net_by_account(_build(m))
    assert net[CAJA_CLP] == Decimal("100000.00")    # plata que entró, NO consumo
    assert net[TC_REAL] == Decimal("-100000.00")
    assert CAT not in net and BANK_CHARGES_ACCOUNT not in net


def test_avance_usd_va_a_caja_us(tmp_path):
    m = _model([("2026-03-10", "AVANCE USD", 200, "avance")], currency="USD")
    entries = build_tc_correction_entries(
        model=m, tc_real_account=TC_REAL, expense_tc_account=EXP_TC, fx=Decimal(900),
        lump_for=lambda tx: abs(tx.amount), category_for=lambda tx: CAT,
        batch_id="b1", bank_account_id="tc-test", emit_opening=False)
    net = _net_by_account(entries)
    assert net[CAJA_USD] == Decimal("180000.00")    # 200 × fx 900, a la Caja USD
    assert CAJA_CLP not in net


def test_op_no_reconocido_va_a_suspense_y_se_reporta(tmp_path):
    m = _model([("2026-03-10", "GLOSA RARA", 5000, "xyz_desconocido")])
    unmapped: list = []
    entries = build_tc_correction_entries(
        model=m, tc_real_account=TC_REAL, expense_tc_account=EXP_TC, fx=Decimal(1),
        lump_for=lambda tx: abs(tx.amount), category_for=lambda tx: CAT,
        batch_id="b1", bank_account_id="tc-test", emit_opening=False, unmapped=unmapped)
    net = _net_by_account(entries)
    assert net[SUSPENSE_ACCOUNT] == Decimal("5000.00")     # nada se descarta
    assert net[TC_REAL] == Decimal("-5000.00")
    assert unmapped == [{"line": 1, "op": "xyz_desconocido", "monto": Decimal("5000")}]
    assert _bean_check(tmp_path, entries) == []


def test_invariante_tc_real_igual_menos_closing(tmp_path):
    # CLP totalmente mapeada con TODOS los tipos: cada línea toca TC:Real → cierra exacto en -closing.
    m = _model([
        ("2026-03-05", "JUMBO", 45000, "compra"),
        ("2026-03-06", "UBER EATS", 12000, None),           # → compra
        ("2026-03-07", "TIMBRE", 781, "impuesto"),          # → GastosBancarios
        ("2026-03-08", "AVANCE", 50000, "avance"),          # → Caja
        ("2026-03-12", "DEVOLUCION", -5000, "abono"),
        ("2026-03-20", "MONTO CANCELADO", -100000, "pago"),
    ], opening="500000")
    net = _net_by_account(_build(m, emit_opening=True))
    assert net[TC_REAL] == -m.balances.closing             # invariante §7: pasivo == -closing
    assert _bean_check(tmp_path, _build(m, emit_opening=True)) == []


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


# ── FX USD: fallback por monto (pagos consolidados Santander, glosa no codifica el USD) ────────


def test_derive_fx_consolidado_elige_posting_por_monto(tmp_path):
    # Santander paga consolidado: la glosa nombra OTRA tarjeta/USD aunque el asiento paga esta cuenta.
    # `load_laudus_entries(expense_tc, ...)` devuelve SOLO el posting a ESTA cuenta-gasto (su CLP). Dos
    # postings (uno por cada tarjeta USD): el matcher debe elegir el de ESTA cuenta por monto (FX ~931),
    # NO el de la otra tarjeta. La glosa no trae 1387.63 → el path de glosa falla, cae al fallback.
    m = _model([("2026-02-10", "AMAZON", 1387.63, "compra")], opening="0", closing="1387.63",
               currency="USD", start="2026-01-28", end="2026-02-28")
    # candidato correcto: 1.291.675 / 1387.63 ≈ 930.8 ; el otro posting (Latanpass) daría FX absurdo aquí.
    us = [
        _us_payment(date(2026, 3, 6), "1291675.00", "USD3.217,07 Visa Santander 0858 Febrero"),
        _us_payment(date(2026, 3, 6), "3000722.00", "USD3.217,07 Visa Santander 0858 Febrero"),
    ]
    res = derive_statement_fx(m, us, bcch=Decimal("931"))
    assert res["status"] == "ok"
    assert res["glosa_usd"] is None                       # eligió por monto, no por glosa
    assert res["lump_clp"] == Decimal("1291675.00")       # el posting de ESTA cuenta
    assert Decimal("930") < res["fx"] < Decimal("932")    # ~930.8, no el del otro posting (3000722/1387.63≈2162)


def test_derive_fx_fallback_bcch_elige_dentro_de_tolerancia(tmp_path):
    # Dos candidatos por monto; con BCCh presente se elige el que cae dentro de tolerancia (5%).
    m = _model([("2026-02-10", "AMAZON", 1000, "compra")], opening="0", closing="1000",
               currency="USD", start="2026-01-28", end="2026-02-28")
    us = [
        _us_payment(date(2026, 3, 5), "1300000.00", "pago consolidado sin USD"),   # FX 1300 ✗ (>tol)
        _us_payment(date(2026, 3, 6), "931000.00", "pago consolidado sin USD"),    # FX 931 ✓
    ]
    res = derive_statement_fx(m, us, bcch=Decimal("931"))
    assert res["status"] == "ok"
    assert res["fx"] == Decimal("931")
    assert res["payment_date"] == date(2026, 3, 6)


def test_derive_fx_fallback_multiples_en_tolerancia_elige_mas_temprano(tmp_path):
    # Varios postings dentro de bcch±tol → elige el de fecha más temprana tras el cierre (§diseño).
    m = _model([("2026-02-10", "AMAZON", 1000, "compra")], opening="0", closing="1000",
               currency="USD", start="2026-01-28", end="2026-02-28")
    us = [
        _us_payment(date(2026, 3, 4), "2000000.00", "pago consolidado"),   # FX 2000 ✗ (fuera tol)
        _us_payment(date(2026, 3, 5), "899000.00", "pago consolidado"),    # FX 899 ✓ (más temprano)
        _us_payment(date(2026, 3, 6), "920000.00", "pago consolidado"),    # FX 920 ✓ pero posterior
    ]
    res = derive_statement_fx(m, us, bcch=Decimal("910"))  # 899 y 920 caen en ±5% de 910
    assert res["status"] == "ok"
    assert res["fx"] == Decimal("899")
    assert res["payment_date"] == date(2026, 3, 5)


def test_derive_fx_sin_bcch_de_referencia_bloquea(tmp_path):
    # Sin BCCh de referencia (ni mes exacto ni último) → no hay ancla → falla segura (bloquea),
    # NO cae a una banda hardcoded (decisión Ary 2026-06-30).
    m = _model([("2026-02-10", "AMAZON", 1000, "compra")], opening="0", closing="1000",
               currency="USD", start="2026-01-28", end="2026-02-28")
    us = [_us_payment(date(2026, 3, 5), "899000.00", "pago consolidado")]  # FX 899, plausible pero sin ancla
    res = derive_statement_fx(m, us, bcch=None)
    assert res["status"] == "blocked" and res["fx"] is None


def test_derive_fx_fallback_sin_candidato_en_tolerancia_sigue_blocked(tmp_path):
    # Ningún posting cae en bcch±tol (ej. Mastercard USD marzo: saldo rodó a abril sin pago propio).
    m = _model([("2026-02-10", "AMAZON", 1000, "compra")], opening="0", closing="1000",
               currency="USD", start="2026-01-28", end="2026-02-28")
    us = [
        _us_payment(date(2026, 3, 5), "578000.00", "pago consolidado"),    # FX 578 ✗
        _us_payment(date(2026, 3, 6), "22955000.00", "pago consolidado"),  # FX 22955 ✗
    ]
    res = derive_statement_fx(m, us, bcch=Decimal("931"))
    assert res["status"] == "blocked" and res["fx"] is None


def test_derive_fx_fallback_gatea_por_mes_del_pago(tmp_path):
    # El estado de feb se paga en MARZO; el gate debe usar el BCCh de marzo (931), no el de feb (861),
    # o el FX ~931 del pago quedaría fuera de tolerancia contra el dólar de febrero (regresión del piloto).
    m = _model([("2026-02-10", "AMAZON", 1387.63, "compra")], opening="0", closing="1387.63",
               currency="USD", start="2026-01-28", end="2026-02-28")
    us = [_us_payment(date(2026, 3, 6), "1291675.00", "pago consolidado sin USD")]  # FX ~930.8
    bcch_by_month = {"2026-02": Decimal("861"), "2026-03": Decimal("931.57")}
    res = derive_statement_fx(m, us, bcch=lambda d: bcch_by_month.get(d.strftime("%Y-%m")))
    assert res["status"] == "ok"
    assert Decimal("930") < res["fx"] < Decimal("932")
    assert res["payment_date"] == date(2026, 3, 6)


def test_derive_fx_glosa_bci_sin_cambios_con_bcch(tmp_path):
    # El path de glosa (BCI) sigue ganando aunque se pase bcch: glosa-USD == closing → FX exacto.
    m = _model([("2026-04-10", "EBAY", 100, "compra")], opening="0", closing="26188.93",
               currency="USD", start="2026-03-28", end="2026-04-28")
    us = [_us_payment(date(2026, 5, 14), "23543848.00", "USD26.188,93 Visa BCI 1027 Abril")]
    res = derive_statement_fx(m, us, bcch=Decimal("899"))
    assert res["status"] == "ok"
    assert res["glosa_usd"] == Decimal("26188.93")        # ganó la glosa, no el fallback
    assert Decimal("898") < res["fx"] < Decimal("900")


# ── Orquestador correct_tc_cartola (end-to-end: staging → ledger) ──────────────

EXPENSE_TC = "Expenses:EAG:TC:TcTest-430099"
TC_REAL_ORCH = "Liabilities:EAG:TC:Real:TcTest"
CAT_SUPER = "Expenses:EAG:Super"

_ORCH_ACCOUNTS = f"""\
2020-12-31 open {EXPENSE_TC} CLP
2020-12-31 open {TC_REAL_ORCH} CLP
2020-12-31 open Expenses:EAG:TC:TcTest2-430100 CLP
2020-12-31 open Liabilities:EAG:TC:Real:TcTest2 CLP
2020-12-31 open {CAT_SUPER} CLP
2020-12-31 open {OPENING_EQUITY} CLP
2020-12-31 open Expenses:EAG:Suspense CLP
2020-12-31 open Assets:EAG:Bancos:Test CLP
2020-12-31 open {BANK_CHARGES_ACCOUNT} CLP
2020-12-31 open {CAJA_CLP} CLP
2020-12-31 open {CAJA_USD} CLP
"""


class _FakeResolved:
    def __init__(self, account, last4):
        self.account, self.last4 = account, last4


class _FakeResolver:
    def __init__(self, account=EXPENSE_TC, last4="1027"):
        self._a, self._l = account, last4

    def resolve(self, bank_account_id):
        return self._a

    def get(self, bank_account_id):
        return _FakeResolved(self._a, self._l)


class _FakePredictor:
    def __init__(self, category=CAT_SUPER):
        self._c = category

    def predict(self, description, amount, bank_account_id):
        return self._c, "test", "*"


class _FakeImporter:
    def __init__(self, resolver=None, predictor=None):
        self.resolver = resolver or _FakeResolver()
        self.category_predictor = predictor or _FakePredictor()


def _make_ledger(tmp_path, *, laudus="", bcch=None):
    """Ledger mínimo (accounts + main con globs) para que bean-check vea las correcciones TC.

    `bcch`: dict {year_month: rate_clp_per_usd} → siembra `_meta/fx-bcch-eom.jsonl` (Story 9.10).
    """
    root = tmp_path / "ledger"
    (root / "imports" / "cartolas" / "_staging").mkdir(parents=True)
    (root / "imports" / "laudus").mkdir(parents=True)
    if bcch is not None:
        import json as _json
        (root / "_meta").mkdir(parents=True)
        (root / "_meta" / "fx-bcch-eom.jsonl").write_text(
            "".join(_json.dumps({"year_month": ym, "rate_clp_per_usd": str(r)}) + "\n"
                    for ym, r in bcch.items()),
            encoding="utf-8")
    (root / "accounts.beancount").write_text(_ORCH_ACCOUNTS, encoding="utf-8")
    (root / "main.beancount").write_text(
        'include "accounts.beancount"\n'
        'include "imports/laudus/*.beancount"\n'
        'include "imports/cartolas/*.beancount"\n', encoding="utf-8")
    # Siempre un archivo laudus (el glob del include exige ≥1 match, como en prod).
    (root / "imports" / "laudus" / "laudus.beancount").write_text(
        laudus or ";; (sin asientos Laudus en este fixture)\n", encoding="utf-8")
    return root


def _stage(root, model, batch_id="b1"):
    path = root / "imports" / "cartolas" / "_staging" / f"{batch_id}.cartola.json"
    path.write_text(model.model_dump_json(indent=2, by_alias=False), encoding="utf-8")
    return path


_TS = "2026-05-20T00:00:00Z"


def test_tc_real_account_deriva_stem_exacto():
    assert tc_real_account("Expenses:EAG:TC:Tc1027VisaInfinity-430005") == \
        "Liabilities:EAG:TC:Real:Tc1027VisaInfinity"
    assert tc_real_account("Expenses:EAG:TC:Tc1027VisaInfinityUs-430006") == \
        "Liabilities:EAG:TC:Real:Tc1027VisaInfinityUs"


def test_correct_clp_end_to_end(tmp_path):
    root = _make_ledger(tmp_path)
    m = _model([
        ("2026-03-10", "JUMBO", 45000, "compra"),
        ("2026-03-12", "DEVOLUCION", -5000, "abono"),
        ("2026-03-20", "MONTO CANCELADO", -100000, "pago"),
    ], opening="500000")
    _stage(root, m)
    res = correct_tc_cartola("b1", _FakeImporter(), root, ts=_TS)

    assert res["status"] == "corrected"
    assert res["purchases"] == 2 and res["payments"] == 1
    assert res["opening_emitted"] is True
    assert res["unmapped"] == []                             # todo mapeó, nada en silencio
    out = root / "imports" / "cartolas"
    files = list(out.glob("*-tc.beancount"))
    assert len(files) == 1                                   # el archivo de corrección se escribió
    assert not (root / "imports" / "cartolas" / "_staging" / "b1.cartola.json").exists()  # staging consumido
    # bean-check del ledger completo pasa
    from beancount import loader
    _e, errors, _o = loader.load_file(str(root / "main.beancount"))
    assert errors == []


def test_correct_clp_reporta_unmapped_sin_bloquear(tmp_path):
    # Una línea con op no reconocido cae a Suspense, se reporta en result["unmapped"], y NO bloquea.
    root = _make_ledger(tmp_path)
    m = _model([("2026-03-10", "JUMBO", 45000, "compra"),
                ("2026-03-11", "GLOSA RARA", 5000, "xyz_desconocido"),
                ("2026-03-20", "MONTO CANCELADO", -50000, "pago")], opening="0")
    _stage(root, m)
    res = correct_tc_cartola("b1", _FakeImporter(), root, ts=_TS)
    assert res["status"] == "corrected"
    assert res["unmapped"] == [{"line": 2, "op": "xyz_desconocido", "monto": Decimal("5000")}]
    from beancount import loader
    _e, errors, _o = loader.load_file(str(root / "main.beancount"))
    assert errors == []                                      # Suspense absorbe; ledger válido


def test_correct_clp_apertura_idempotente(tmp_path):
    root = _make_ledger(tmp_path)
    # 1ra cartola → emite apertura
    m1 = _model([("2026-03-10", "JUMBO", 45000, "compra")], opening="500000",
                start="2026-03-01", end="2026-03-31")
    _stage(root, m1, "b1")
    r1 = correct_tc_cartola("b1", _FakeImporter(), root, ts=_TS)
    assert r1["opening_emitted"] is True
    # 2da cartola de la MISMA tarjeta → NO repite apertura
    m2 = _model([("2026-04-10", "LIDER", 30000, "compra")], opening="545000",
                start="2026-04-01", end="2026-04-30")
    _stage(root, m2, "b2")
    r2 = correct_tc_cartola("b2", _FakeImporter(), root, ts=_TS)
    assert r2["status"] == "corrected"
    assert r2["opening_emitted"] is False
    # solo una apertura en todo el ledger
    from beancount import loader
    entries, errors, _o = loader.load_file(str(root / "main.beancount"))
    assert errors == []
    aperturas = [e for e in entries if isinstance(e, data.Transaction)
                 and (e.meta or {}).get("operation_type") == "apertura"]
    assert len(aperturas) == 1


def test_correct_bloquea_si_moneda_no_coincide_con_la_cuenta(tmp_path):
    # Cuenta USD (TC:Real ...Us) pero cartola extraída como CLP → guard bloquea (no postea la deuda a
    # fx=1). Es el caso real de la 1027 USD abril leída como CLP por Gemini.
    root = _make_ledger(tmp_path)
    m = _model([("2026-03-10", "EBAY", 100, "compra")], currency="CLP")   # CLP...
    _stage(root, m)
    usd_resolver = _FakeResolver(account="Expenses:EAG:TC:TcTestUs-430200", last4="1027")  # ...cuenta USD
    res = correct_tc_cartola("b1", _FakeImporter(resolver=usd_resolver), root, ts=_TS)
    assert res["status"] == "blocked"
    assert "moneda no coincide" in res["reason"]
    assert list((root / "imports" / "cartolas").glob("*-tc.beancount")) == []  # no posteó nada


# datos reales: estado 28/03→28/04 closing USD26.188,93, saldado 14/05 con 23.543.848 CLP;
# el MONTO CANCELADO interno (paga el período anterior, USD5.000) se saldó con 4.500.000 CLP.
_USD_LAUDUS = (
    '2026-04-10 * "USD5.000,00 Visa Test 1234 Marzo"\n'
    '  Assets:EAG:Bancos:Test  -4500000.00 CLP\n'
    f'  {EXPENSE_TC}  4500000.00 CLP\n'
    '\n'
    '2026-05-14 * "USD26.188,93 Visa Test 1234 Abril"\n'
    '  Assets:EAG:Bancos:Test  -23543848.00 CLP\n'
    f'  {EXPENSE_TC}  23543848.00 CLP\n'
)


def _usd_model(closing="26188.93"):
    return _model([
        ("2026-04-05", "EBAY", 13094.46, "compra"),
        ("2026-04-15", "AMAZON", 13094.47, "compra"),
        ("2026-04-20", "MONTO CANCELADO", -5000, "pago"),
    ], opening="5000", closing=closing, currency="USD", start="2026-03-28", end="2026-04-28")


def test_correct_usd_end_to_end(tmp_path):
    # FX derivado ≈ 898.99; BCCh del mes DEL PAGO (2026-05, el pago que salda es del 14-may) ≈ 899 →
    # dentro de tolerancia → corrected.
    root = _make_ledger(tmp_path, laudus=_USD_LAUDUS, bcch={"2026-05": 899})
    _stage(root, _usd_model())
    res = correct_tc_cartola("b1", _FakeImporter(), root, ts=_TS)

    assert res["status"] == "corrected", res["reason"]
    assert res["fx"] is not None and Decimal("898") < Decimal(res["fx"]) < Decimal("900")
    assert res["fx_deviation_pct"] is not None and res["fx_deviation_pct"] < 5.0  # cuadra vs BCCh
    from beancount import loader
    _e, errors, _o = loader.load_file(str(root / "main.beancount"))
    assert errors == []


def test_correct_usd_bloqueante_sin_pago_que_salde(tmp_path):
    # Laudus solo tiene el pago del MONTO CANCELADO, NO el que salda el closing → FX bloqueante.
    laudus = ('2026-04-10 * "USD5.000,00 Visa Test 1234 Marzo"\n'
              '  Assets:EAG:Bancos:Test  -4500000.00 CLP\n'
              f'  {EXPENSE_TC}  4500000.00 CLP\n')
    root = _make_ledger(tmp_path, laudus=laudus)
    _stage(root, _usd_model())
    res = correct_tc_cartola("b1", _FakeImporter(), root, ts=_TS)
    assert res["status"] == "blocked"
    assert not list((root / "imports" / "cartolas").glob("*-tc.beancount"))  # no escribió nada


def test_correct_usd_saldo_arrastrado_no_bloquea(tmp_path):
    # Regresión del fix de cuadre: estado que arrastra saldo (opening 5000, MONTO CANCELADO paga solo
    # 3000 → revolving, closing=28188.93). El viejo check `residuo` lo bloqueaba como "descuadre"; pero
    # es un estado CORRECTO (la apertura captura el saldo arrastrado). Con FX derivado ≈ 898.97 dentro
    # de tolerancia BCCh → NO debe bloquear.
    laudus = (
        '2026-04-10 * "USD3.000,00 Visa Test 1234 Marzo"\n'
        '  Assets:EAG:Bancos:Test  -2700000.00 CLP\n'
        f'  {EXPENSE_TC}  2700000.00 CLP\n'
        '\n'
        '2026-05-14 * "USD28.188,93 Visa Test 1234 Abril"\n'
        '  Assets:EAG:Bancos:Test  -25341000.00 CLP\n'
        f'  {EXPENSE_TC}  25341000.00 CLP\n'
    )
    root = _make_ledger(tmp_path, laudus=laudus, bcch={"2026-05": 899})
    m = _model([
        ("2026-04-05", "EBAY", 13094.46, "compra"),
        ("2026-04-15", "AMAZON", 13094.47, "compra"),
        ("2026-04-20", "MONTO CANCELADO", -3000, "pago"),
    ], opening="5000", closing="28188.93", currency="USD", start="2026-03-28", end="2026-04-28")
    _stage(root, m)
    res = correct_tc_cartola("b1", _FakeImporter(), root, ts=_TS)
    assert res["status"] == "corrected", res["reason"]


def test_correct_usd_bloqueante_si_fx_fuera_de_tolerancia(tmp_path):
    # FX derivado del pago ≈ 898.99, pero el BCCh del mes del pago (2026-05) está en 700 → desviación
    # ~28% > 5% → señal de que el lump o el total USD no corresponden → bloqueante.
    root = _make_ledger(tmp_path, laudus=_USD_LAUDUS, bcch={"2026-05": 700})
    _stage(root, _usd_model())
    res = correct_tc_cartola("b1", _FakeImporter(), root, ts=_TS)
    assert res["status"] == "blocked"
    assert "BCCh" in res["reason"] and "fx-out-of-tolerance" in res["reason"]
    assert not list((root / "imports" / "cartolas").glob("*-tc.beancount"))  # no escribió nada


def test_correct_usd_sin_bcch_no_bloquea(tmp_path):
    # Sin dólar BCCh ese mes (Story 9.10 no corrió) → no se puede validar, pero NO se bloquea
    # (mismo criterio que 9.6b: fx-bcch-missing procede).
    root = _make_ledger(tmp_path, laudus=_USD_LAUDUS)  # sin bcch
    _stage(root, _usd_model())
    res = correct_tc_cartola("b1", _FakeImporter(), root, ts=_TS)
    assert res["status"] == "corrected", res["reason"]
    assert res["fx_deviation_pct"] is None


def test_validate_balance_rutea_tc_a_correccion(tmp_path, monkeypatch):
    # AC1: una cartola con account_type tarjeta_credito entra al modo corrección TC (postea),
    # NO al modelo A de reconciliación-sin-postear.
    from backend.app.api.v1.cartolas import service

    root = _make_ledger(tmp_path)
    m = _model([("2026-03-10", "JUMBO", 45000, "compra"),
                ("2026-03-20", "MONTO CANCELADO", -45000, "pago")], opening="0")
    _stage(root, m)
    out = service.validate_balance(
        "b1", opening=0, closing=0, override_justification=None,
        user_email="t@t.cl", ledger_root=root, importer=_FakeImporter(), now_iso=_TS)
    assert out["status"] == "corrected"
    assert out["currency"] == "CLP"
    assert list((root / "imports" / "cartolas").glob("*-tc.beancount"))


def test_correct_re_import_preserva_apertura(tmp_path):
    # Re-importar la MISMA cartola (mismo slug → se sobrescribe su archivo) NO debe perder la apertura:
    # `_opening_exists` se salta el archivo destino de ESTA corrida, así re-emite en vez de borrarla.
    root = _make_ledger(tmp_path)
    m = _model([("2026-03-10", "JUMBO", 45000, "compra")], opening="500000",
               start="2026-03-01", end="2026-03-31")
    _stage(root, m, "b1")
    r1 = correct_tc_cartola("b1", _FakeImporter(), root, ts=_TS)
    assert r1["opening_emitted"] is True
    # re-stage idéntico y re-correr (mismo slug → mismo archivo)
    _stage(root, m, "b1")
    r2 = correct_tc_cartola("b1", _FakeImporter(), root, ts=_TS)
    assert r2["opening_emitted"] is True                      # NO se perdió la apertura al re-importar
    from beancount import loader
    entries, errors, _o = loader.load_file(str(root / "main.beancount"))
    assert errors == []
    aperturas = [e for e in entries if isinstance(e, data.Transaction)
                 and (e.meta or {}).get("operation_type") == "apertura"]
    assert len(aperturas) == 1                                # exactamente una (sobrescribió, no duplicó)


def test_slug_desambigua_tarjetas_mismo_last4(tmp_path):
    # Dos tarjetas distintas (mismo banco + last4 + mes) pero distinto stem de cuenta NO deben colisionar
    # en el mismo `{slug}-tc.beancount`. Antes el slug = banco-last4-mes → la 2da sobrescribía a la 1ra.
    root = _make_ledger(tmp_path)
    m1 = _model([("2026-03-10", "JUMBO", 45000, "compra")], opening="0",
                start="2026-03-01", end="2026-03-31")
    _stage(root, m1, "b1")
    r1 = correct_tc_cartola("b1", _FakeImporter(_FakeResolver(EXPENSE_TC, "1027")), root, ts=_TS)
    m2 = _model([("2026-03-12", "LIDER", 30000, "compra")], opening="0",
                start="2026-03-01", end="2026-03-31")
    _stage(root, m2, "b2")
    r2 = correct_tc_cartola(
        "b2", _FakeImporter(_FakeResolver("Expenses:EAG:TC:TcTest2-430100", "1027")), root, ts=_TS)
    assert r1["status"] == "corrected" and r2["status"] == "corrected", (r1["reason"], r2["reason"])
    files = sorted(p.name for p in (root / "imports" / "cartolas").glob("*-tc.beancount"))
    assert len(files) == 2, files                             # dos archivos distintos, sin sobrescritura


# ── FX heredado para meses revolving (brief Valentina 2026-07-06) ──────────────
# Datos reales 8996 Mastercard USD: marzo cerró en US$2.234,84 SIN pago propio (rodó a abril);
# abril (opening 2.234,84) se saldó el 08-05 a fx 899,64 → marzo hereda ese fx (costo real pagado).
# BCCh marzo 2026 = 931,57 → desviación del heredado 3,4% < 5% (pasa el gate).

_FX_ABRIL = "899.6399966540679816927715418"


def _marzo_revolving_model():
    # opening 1.387,63 (cierre de feb) − pago 1.387,63 (salda feb, 06-03) + movimientos 2.234,84
    # = closing 2.234,84 (nadie lo pagó dentro de la ventana → revolving).
    return _model([
        ("2026-03-06", "MONTO CANCELADO", -1387.63, "pago"),
        ("2026-03-15", "COMPRAS DEL MES", 2234.84, "compra"),
    ], opening="1387.63", closing="2234.84", currency="USD", start="2026-02-25", end="2026-03-24")


def _write_imported_tc(out_dir, *, period="2026-04", opening="2234.84", closing="57024.47",
                       fx=_FX_ABRIL, fx_source=None, account=TC_REAL_ORCH, currency="USD"):
    """Simula una cartola TC YA importada (metadata 6.6) para que `inherit_statement_fx` la escanee."""
    stem = account.rsplit(":", 1)[-1]
    lines = [
        '2026-04-10 * "COMPRA PREVIA"',
        '  source: "cartola-tc"',
        '  bank_account_id: "tc-test"',
        '  batch_id: "bprev"',
        '  line: "1"',
        '  operation_type: "compra"',
        f'  period: "{period}"',
        f'  opening: "{opening}"',
        f'  closing: "{closing}"',
        f'  currency: "{currency}"',
        f'  fx: "{fx}"',
    ]
    if fx_source:
        lines.append(f'  fx_source: "{fx_source}"')
    lines += [f'  {account}  -89964.00 CLP', '  Expenses:EAG:Suspense  89964.00 CLP', '']
    path = out_dir / f"Banco-1027-{stem}-{period}-tc.beancount"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_inherit_fx_hereda_del_estado_que_absorbe(tmp_path):
    _write_imported_tc(tmp_path)
    res = inherit_statement_fx(_marzo_revolving_model(), TC_REAL_ORCH, tmp_path,
                               bcch_ref=Decimal("931.57"))
    assert res["status"] == "ok"
    assert res["fx"] == Decimal(_FX_ABRIL)
    assert res["fx_source"] == "inherited:2026-04"            # origen = abril (pago real)
    assert res["inherited_from"] == "2026-04"


def test_inherit_fx_bloquea_sin_estado_siguiente(tmp_path):
    res = inherit_statement_fx(_marzo_revolving_model(), TC_REAL_ORCH, tmp_path,
                               bcch_ref=Decimal("931.57"))
    assert res["status"] == "blocked"
    assert "importá primero el mes siguiente" in res["reason"]


def test_inherit_fx_bloquea_sin_contiguidad(tmp_path):
    # El estado posterior existe pero su apertura NO es el cierre de este (no lo absorbió).
    _write_imported_tc(tmp_path, opening="9999.99")
    res = inherit_statement_fx(_marzo_revolving_model(), TC_REAL_ORCH, tmp_path,
                               bcch_ref=Decimal("931.57"))
    assert res["status"] == "blocked"


def test_inherit_fx_gate_bcch_aplica(tmp_path):
    # Sin BCCh de referencia → falla segura; con BCCh lejano (700 vs 899,64 = 28%) → bloquea.
    _write_imported_tc(tmp_path)
    m = _marzo_revolving_model()
    assert inherit_statement_fx(m, TC_REAL_ORCH, tmp_path, bcch_ref=None)["status"] == "blocked"
    res = inherit_statement_fx(m, TC_REAL_ORCH, tmp_path, bcch_ref=Decimal("700"))
    assert res["status"] == "blocked"
    assert "gate BCCh" in res["reason"]


def test_inherit_fx_ignora_otra_moneda_y_periodo_anterior(tmp_path):
    # Una cartola CLP contigua o un estado ANTERIOR no son fuentes de herencia.
    _write_imported_tc(tmp_path, currency="CLP")
    _write_imported_tc(tmp_path, period="2026-01")
    res = inherit_statement_fx(_marzo_revolving_model(), TC_REAL_ORCH, tmp_path,
                               bcch_ref=Decimal("931.57"))
    assert res["status"] == "blocked"


def test_inherit_fx_origen_propaga_y_acota_la_cadena(tmp_path):
    # El estado que absorbe puede haber heredado a su vez: el ORIGEN (pago real) se propaga y la
    # cadena se acota a 3 meses — deuda impaga más larga sigue bloqueada (revisión humana).
    m = _marzo_revolving_model()
    _write_imported_tc(tmp_path, fx_source="inherited:2026-05")
    ok = inherit_statement_fx(m, TC_REAL_ORCH, tmp_path, bcch_ref=Decimal("931.57"))
    assert ok["status"] == "ok" and ok["fx_source"] == "inherited:2026-05"   # propaga el origen
    _write_imported_tc(tmp_path, fx_source="inherited:2026-07")              # origen a 4 meses
    far = inherit_statement_fx(m, TC_REAL_ORCH, tmp_path, bcch_ref=Decimal("931.57"))
    assert far["status"] == "blocked"
    assert "cadena revolving" in far["reason"]


def test_correct_usd_revolving_hereda_fx_end_to_end(tmp_path):
    # El caso real completo: marzo staged + abril ya importado + el pago de feb en Laudus (consolidado
    # Santander: la glosa nombra otro USD) → marzo postea con fx heredado de abril, apertura al CLP
    # real del pago de feb, y metadata fx_source auditable.
    laudus = ('2026-03-06 * "USD3.217,07 Visa Santander Febrero 2026"\n'
              '  Assets:EAG:Bancos:Test  -1291675.00 CLP\n'
              f'  {EXPENSE_TC}  1291675.00 CLP\n')
    root = _make_ledger(tmp_path, laudus=laudus, bcch={"2026-03": Decimal("931.57")})
    out_dir = root / "imports" / "cartolas"
    _write_imported_tc(out_dir)
    _stage(root, _marzo_revolving_model())
    res = correct_tc_cartola("b1", _FakeImporter(), root, ts=_TS)

    assert res["status"] == "corrected", res["reason"]
    assert res["fx_source"] == "inherited:2026-04"
    assert res["fx"] == _FX_ABRIL
    (marzo_file,) = out_dir.glob("*-TcTest-2026-03-tc.beancount")
    assert 'fx_source: "inherited:2026-04"' in marzo_file.read_text(encoding="utf-8")
    from beancount import loader
    entries, errors, _o = loader.load_file(str(root / "main.beancount"))
    assert errors == []
    # Apertura valorizada al CLP REAL del pago que la salda (1.291.675), no a opening×fx heredado.
    aperturas = [e for e in entries if isinstance(e, data.Transaction)
                 and (e.meta or {}).get("operation_type") == "apertura"]
    assert len(aperturas) == 1
    (tc_leg,) = [p for p in aperturas[0].postings if p.account == TC_REAL_ORCH]
    assert tc_leg.units.number == Decimal("-1291675.00")


def test_correct_usd_revolving_bloquea_sin_mes_siguiente(tmp_path):
    # Revolving pero el estado que lo absorbió NO está importado → sigue bloqueando, con mensaje
    # accionable (importá primero el mes siguiente).
    root = _make_ledger(tmp_path, bcch={"2026-03": Decimal("931.57")})
    _stage(root, _marzo_revolving_model())
    res = correct_tc_cartola("b1", _FakeImporter(), root, ts=_TS)
    assert res["status"] == "blocked"
    assert "importá primero el mes siguiente" in res["reason"]
    assert not list((root / "imports" / "cartolas").glob("*-tc.beancount"))  # no escribió nada
