"""Story 6.5b — reconciliación period-aware (el período es un campo, no la fecha de la tx).

Cubre:
- Ventana de matching cuenta corriente padeada ±DATE_TOLERANCE_DAYS (asiento Laudus del borde,
  fechado fuera del período, ahora matchea en vez de ser `missing-in-laudus` falso).
- `missing-in-cartola` acotado al período core (el padding NO debe flaggear asientos de estados
  adyacentes).
- El servicio agrupa por el período persistido (`year_month`), no por la fecha de la tx.
- Los asientos de corrección de TC llevan metadata `period`.
"""
import json

import pytest

from backend.app.api.v1.cartolas.service import validate_balance  # noqa: F401 (paridad imports test 6.1)
from backend.app.api.v1.reconciliation.service import read_discrepancies
from pipeline.importers.bank_account_resolver import BankAccountResolver
from pipeline.importers.cartola_pdf_importer import CartolaPdfImporter
from pipeline.importers.reconcile import reconcile_cartola

CC_ID = "11111111-1111-1111-1111-111111111111"
ACCOUNT = "Assets:EAG:Bancos:CtaCorriente-100200"

ACCOUNTS = """\
2020-12-31 open Assets:EAG:Bancos:CtaCorriente-100200 CLP
  bank_account_id: "11111111-1111-1111-1111-111111111111"
  bank_account_type: "cta_corriente"
  bank_account_currency: "CLP"
  bank_account_last4: "0200"
  bank_name: "Banco BCI"
2020-12-31 open Expenses:EAG:Suspense CLP, USD
2020-12-31 open Expenses:EAG:Super CLP
2020-12-31 open Equity:Reconciliation:Discrepancias CLP, USD
"""


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("IMPORTER_GIT_ENABLED", raising=False)
    monkeypatch.delenv("LEDGER_DISCREPANCIES", raising=False)


def _root(tmp_path):
    (tmp_path / "imports" / "cartolas" / "_staging").mkdir(parents=True, exist_ok=True)
    (tmp_path / "imports" / "laudus").mkdir(parents=True, exist_ok=True)
    (tmp_path / "accounts.beancount").write_text(ACCOUNTS, encoding="utf-8")
    return tmp_path


def _laudus(root, entries_text):
    # El nombre del archivo no importa: load_laudus_entries filtra por fecha, no por nombre.
    (root / "imports" / "laudus" / "laudus.beancount").write_text(entries_text, encoding="utf-8")


def _entry(date_iso, desc, amount):
    return f'{date_iso} * "{desc}"\n  {ACCOUNT}  {amount} CLP\n  Expenses:EAG:Super  {-amount} CLP\n'


def _staging(root, txs, batch_id="b1", opening="0", closing=None):
    if closing is None:
        closing = str(int(opening) + sum(a for _, _, a in txs))
    payload = {
        "schema_version": "1.0",
        "source": {"bank_account_id": CC_ID, "bank_name": "Banco BCI", "account_label": "CC",
                   "account_type": "cta_corriente", "entity": "EAG"},
        "period": {"start": "2026-03-01", "end": "2026-03-31"},
        "currency": "CLP",
        "balances": {"opening": opening, "closing": closing},
        "transactions": [{"line_no": i + 1, "date": d, "description": desc, "amount": str(a),
                          "currency": "CLP", "raw": {}} for i, (d, desc, a) in enumerate(txs)],
        "extraction": {"model": "test", "extracted_at": "2026-04-01T10:00:00Z", "warnings": []},
    }
    (root / "imports" / "cartolas" / "_staging" / f"{batch_id}.cartola.json").write_text(
        json.dumps(payload), encoding="utf-8")


def _importer(root):
    return CartolaPdfImporter(BankAccountResolver(root / "accounts.beancount"))


def _disc_lines(root):
    p = root / "_meta" / "cartola-discrepancies.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


# ── (a) Laudus del borde (fuera del período) ahora matchea con el padding ──────


def test_padding_matchea_asiento_del_borde(tmp_path):
    root = _root(tmp_path)
    # Asiento Laudus fechado 2026-02-28 (fuera de [03-01, 03-31]) pero a 1 día de la línea de cartola.
    _laudus(root, _entry("2026-02-28", "JUMBO", -45000))
    _staging(root, [("2026-03-01", "JUMBO", -45000)])
    res = reconcile_cartola("b1", _importer(root), root, ts="t")
    # Antes de 6.5b: missing-in-laudus falso (la ventana exacta no cargaba el 02-28). Ahora matchea
    # su contraparte y queda como soft `date-mismatch` (las fechas exactas difieren 1d), no como falta.
    states = [d["state"] for d in _disc_lines(root)]
    assert "missing-in-laudus" not in states
    assert states == ["date-mismatch"]
    assert res["differences"] == 1 and res["blocking"] == 0


# ── (b) padding NO crea missing-in-cartola de estados adyacentes ──────────────


def test_padding_no_crea_missing_in_cartola_fuera_de_core(tmp_path):
    root = _root(tmp_path)
    _laudus(root, _entry("2026-03-15", "JUMBO", -45000)        # dentro del core → matchea
            + _entry("2026-04-02", "SOLO-LAUDUS", -12000))     # fuera del core (estado siguiente)
    _staging(root, [("2026-03-15", "JUMBO", -45000)])
    res = reconcile_cartola("b1", _importer(root), root, ts="t")
    assert _disc_lines(root) == []          # el asiento del 04-02 NO se flaggea
    assert res["differences"] == 0 and res["blocking"] == 0 and res["matched"] == 1


# ── (c) missing-in-cartola dentro del core SÍ se emite (no se acota de más) ────


def test_missing_in_cartola_dentro_de_core_se_emite(tmp_path):
    root = _root(tmp_path)
    _laudus(root, _entry("2026-03-15", "JUMBO", -45000)
            + _entry("2026-03-20", "SOLO-LAUDUS", -12000))     # dentro del core, sin línea de cartola
    _staging(root, [("2026-03-15", "JUMBO", -45000)])
    res = reconcile_cartola("b1", _importer(root), root, ts="t")
    assert [d["state"] for d in _disc_lines(root)] == ["missing-in-cartola"]
    assert res["blocking"] == 1 and res["matched"] == 1


# ── (d) la discrepancia lleva year_month = período del estado; el servicio agrupa por él ──


def test_discrepancia_persiste_periodo_del_estado(tmp_path):
    root = _root(tmp_path)
    _laudus(root, "")  # vacío → la línea queda missing-in-laudus
    _staging(root, [("2026-03-10", "TRANSFER", -9999)])
    reconcile_cartola("b1", _importer(root), root, ts="t")
    lines = _disc_lines(root)
    assert len(lines) == 1
    assert lines[0]["year_month"] == "2026-03"  # = model.period.end, persistido


def test_servicio_agrupa_por_periodo_persistido_no_por_fecha(tmp_path, monkeypatch):
    # Discrepancia cuyo período de estado (2026-03) difiere del mes de la fecha de la tx (2026-02).
    jsonl = tmp_path / "disc.jsonl"
    rec = {"schema_version": "1.0", "discrepancy_id": "d1", "ts": "t", "batch_id": "b1",
           "bank_account_id": CC_ID, "year_month": "2026-03", "state": "missing-in-laudus",
           "source": "cartola",
           "cartola": {"line_no": 1, "date": "2026-02-15", "amount": -100.0, "currency": "CLP",
                       "description": "X"},
           "laudus": None, "fx": {"implied": None, "bcch": None, "deviation_pct": None},
           "resolution": None}
    jsonl.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    monkeypatch.setenv("LEDGER_DISCREPANCIES", str(jsonl))
    # Agrupa por el período persistido (2026-03), no por la fecha de la tx (2026-02).
    assert read_discrepancies(year_month="2026-03")["summary"]["total"] == 1
    assert read_discrepancies(year_month="2026-02")["summary"]["total"] == 0


def test_servicio_fallback_a_fecha_si_no_hay_periodo(tmp_path, monkeypatch):
    # Discrepancia vieja sin year_month → cae a la fecha de la tx (backward-compat).
    jsonl = tmp_path / "disc.jsonl"
    rec = {"schema_version": "1.0", "discrepancy_id": "d1", "ts": "t", "batch_id": "b1",
           "bank_account_id": CC_ID, "state": "missing-in-laudus", "source": "cartola",
           "cartola": {"line_no": 1, "date": "2026-02-15", "amount": -100.0, "currency": "CLP",
                       "description": "X"},
           "laudus": None, "fx": {"implied": None, "bcch": None, "deviation_pct": None},
           "resolution": None}
    jsonl.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    monkeypatch.setenv("LEDGER_DISCREPANCIES", str(jsonl))
    assert read_discrepancies(year_month="2026-02")["summary"]["total"] == 1


# ── (e) los asientos de corrección de TC llevan metadata `period` ─────────────


def test_tc_correction_lleva_meta_period():
    from decimal import Decimal

    from backend.app.integrations.cartola_schema import CartolaCanonicalV1
    from pipeline.importers.tc_correction import build_tc_correction_entries

    payload = {
        "schema_version": "1.0",
        "source": {"bank_account_id": "tc-test", "bank_name": "Banco Test",
                   "account_label": "Visa Test 1234", "account_type": "tarjeta_credito", "entity": "EAG"},
        "period": {"start": "2026-03-01", "end": "2026-03-31"},
        "currency": "CLP",
        "balances": {"opening": "500000", "closing": "545000"},
        "transactions": [{"line_no": 1, "date": "2026-02-28", "description": "JUMBO", "amount": "45000",
                          "currency": "CLP", "raw": {"operation_type": "compra"}}],
        "extraction": {"model": "test", "extracted_at": "2026-04-01T00:00:00Z", "warnings": []},
    }
    model = CartolaCanonicalV1.model_validate(payload)
    entries = build_tc_correction_entries(
        model=model, tc_real_account="Liabilities:EAG:TC:Real:VisaTest1234",
        expense_tc_account="Expenses:EAG:TC:VisaTest1234-430005", fx=Decimal(1),
        lump_for=lambda tx: abs(tx.amount), category_for=lambda tx: "Expenses:EAG:Super",
        batch_id="b1", bank_account_id="tc-test", emit_opening=True,
    )
    assert entries  # compra + apertura
    # Todos los asientos llevan period = período del estado (2026-03), distinto de la fecha (2026-02-28).
    assert all(e.meta.get("period") == "2026-03" for e in entries)
    compra = next(e for e in entries if e.meta.get("operation_type") == "compra")
    assert compra.date.strftime("%Y-%m") == "2026-02"  # la fecha de la compra ES de otro mes
