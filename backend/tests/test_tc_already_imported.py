"""Tests del aviso 'cartola ya importada' — evita re-subir por error (resetea categorizaciones)."""
from datetime import date
from types import SimpleNamespace

from backend.app.api.v1.cartolas.service import tc_cartola_already_imported
from pipeline.importers.tc_correction import tc_cartola_filename


def test_filename_distingue_tarjeta_moneda_mes():
    clp = tc_cartola_filename("Banco BCI", "1027",
                              "Liabilities:EAG:TC:Real:Tc1027VisaInfinity", date(2026, 4, 28))
    assert "-1027-" in clp and clp.endswith("Tc1027VisaInfinity-2026-04-tc.beancount")
    # USD (stem con Us) y otro mes → archivos distintos.
    usd = tc_cartola_filename("Banco BCI", "1027",
                              "Liabilities:EAG:TC:Real:Tc1027VisaInfinityUs", date(2026, 4, 28))
    mar = tc_cartola_filename("Banco BCI", "1027",
                              "Liabilities:EAG:TC:Real:Tc1027VisaInfinity", date(2026, 3, 27))
    assert clp != usd and clp != mar


def _canonical(account_type="tarjeta_credito"):
    return SimpleNamespace(
        source=SimpleNamespace(account_type=account_type, bank_account_id="card-x"),
        period=SimpleNamespace(end=date(2026, 4, 28)))


def _index():
    entry = SimpleNamespace(beancount_account="Expenses:EAG:TC:Tc1027VisaInfinity-430005",
                            bank_name="Banco BCI", last4="1027")
    return SimpleNamespace(get=lambda _id: entry)


def test_avisa_solo_si_el_archivo_ya_existe(tmp_path):
    assert tc_cartola_already_imported(_canonical(), _index(), tmp_path) is False
    fn = tc_cartola_filename("Banco BCI", "1027",
                             "Liabilities:EAG:TC:Real:Tc1027VisaInfinity", date(2026, 4, 28))
    (tmp_path / fn).write_text(";; ya importada\n", encoding="utf-8")
    assert tc_cartola_already_imported(_canonical(), _index(), tmp_path) is True


def test_no_avisa_para_cuenta_no_tc(tmp_path):
    assert tc_cartola_already_imported(_canonical("cuenta_corriente"), _index(), tmp_path) is False
