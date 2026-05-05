"""Tests para bootstrap.generate_accounts — Story 9.1 Task 2."""
import csv

from bootstrap.generate_accounts import (
    crosscheck,
    index_bank_accounts,
    render_accounts_beancount,
    render_open_directive,
    run_bootstrap,
)


# ── Fixtures ─────────────────────────────────────────────────────────────

# Laudus shape: longitud variable según jerarquía
LAUDUS_FIXTURE = [
    {"accountId": 1, "accountNumber": "1", "name": "ACTIVO EAG", "notes": ""},
    {"accountId": 2, "accountNumber": "11", "name": "ACTIVOS CORRIENTES", "notes": ""},
    {"accountId": 3, "accountNumber": "111", "name": "DISPONIBLE - EAG", "notes": ""},
    {"accountId": 4, "accountNumber": "111005", "name": "Banco BCI - 10160175", "notes": ""},
    {"accountId": 5, "accountNumber": "215001", "name": "VISA Infinity Eduardo", "notes": ""},
    {"accountId": 6, "accountNumber": "413044", "name": "Combustible Vehículos", "notes": ""},
]

# Supabase shape: todo padded a 6
SUPABASE_PLAN_FIXTURE = [
    {"account_number": "100000", "account_name": "ACTIVO EAG", "cat1": "ACTIVO EAG",
     "cat2": "ACTIVO EAG", "cat3": "ACTIVO EAG", "active": True},
    {"account_number": "110000", "account_name": "ACTIVOS CORRIENTES", "cat1": "ACTIVO EAG",
     "cat2": "ACTIVOS CORRIENTES", "cat3": "ACTIVOS CORRIENTES", "active": True},
    {"account_number": "111000", "account_name": "DISPONIBLE - EAG", "cat1": "ACTIVO EAG",
     "cat2": "DISPONIBLE", "cat3": "DISPONIBLE", "active": True},
    {"account_number": "111005", "account_name": "Banco BCI - 10160175", "cat1": "ACTIVO EAG",
     "cat2": "Banco / Caja", "cat3": "Banco BCI", "active": True},
    {"account_number": "215001", "account_name": "VISA Infinity Eduardo", "cat1": "PASIVO",
     "cat2": "TC", "cat3": "Eduardo", "active": True},
    {"account_number": "413044", "account_name": "Combustible Vehículos", "cat1": "GASTOS - EGRESOS",
     "cat2": "Vehículos", "cat3": "Combustible", "active": True},
]

SUPABASE_BANKS_FIXTURE = [
    {"id": "uuid-bci-001", "account_number": "111005", "account_type": "cta_corriente",
     "account_currency": "CLP", "bank_name": "BCI", "active": True},
    {"id": "uuid-visa-001", "account_number": "215001", "account_type": "tarjeta_credito",
     "account_currency": "USD", "bank_name": "BCI", "active": True},
]


# ── Crosscheck ───────────────────────────────────────────────────────────

class TestCrosscheck:
    def test_normalizes_padding_correctly(self):
        result = crosscheck(LAUDUS_FIXTURE, SUPABASE_PLAN_FIXTURE)
        # 6 cuentas en cada fuente, todas matchean tras normalización
        assert len(result.matched) == 6
        assert result.laudus_only == []
        assert result.supabase_only == []
        assert result.name_divergences == []

    def test_records_carry_original_laudus_length(self):
        result = crosscheck(LAUDUS_FIXTURE, SUPABASE_PLAN_FIXTURE)
        by_num = {r["account_number"]: r for r in result.matched}
        assert by_num["100000"]["laudus_original_length"] == 1
        assert by_num["110000"]["laudus_original_length"] == 2
        assert by_num["111000"]["laudus_original_length"] == 3
        assert by_num["111005"]["laudus_original_length"] == 6

    def test_detects_laudus_only(self):
        sup = [r for r in SUPABASE_PLAN_FIXTURE if r["account_number"] != "413044"]
        result = crosscheck(LAUDUS_FIXTURE, sup)
        assert any(r["account_number"] == "413044" for r in result.laudus_only)

    def test_detects_supabase_only(self):
        laud = [a for a in LAUDUS_FIXTURE if a["accountNumber"] != "111005"]
        result = crosscheck(laud, SUPABASE_PLAN_FIXTURE)
        assert any(r["account_number"] == "111005" for r in result.supabase_only)

    def test_detects_name_divergence(self):
        sup_with_typo = [
            {**r, "account_name": "Banco BCI typo"} if r["account_number"] == "111005" else r
            for r in SUPABASE_PLAN_FIXTURE
        ]
        result = crosscheck(LAUDUS_FIXTURE, sup_with_typo)
        divergences = {d["account_number"]: d for d in result.name_divergences}
        assert "111005" in divergences
        assert divergences["111005"]["laudus_name"] == "Banco BCI - 10160175"
        assert divergences["111005"]["supabase_name"] == "Banco BCI typo"

    def test_has_structural_mismatches_property(self):
        clean = crosscheck(LAUDUS_FIXTURE, SUPABASE_PLAN_FIXTURE)
        assert clean.has_structural_mismatches is False
        # Solo laudus-only / supabase-only son estructurales y bloquean.
        # name-divergence NO bloquea bajo policy "Laudus manda".
        dirty_structural = crosscheck(LAUDUS_FIXTURE, SUPABASE_PLAN_FIXTURE[:-1])
        assert dirty_structural.has_structural_mismatches is True
        sup_with_typo = [
            {**r, "account_name": "Banco BCI typo"} if r["account_number"] == "111005" else r
            for r in SUPABASE_PLAN_FIXTURE
        ]
        only_divergence = crosscheck(LAUDUS_FIXTURE, sup_with_typo)
        assert only_divergence.has_structural_mismatches is False
        assert only_divergence.name_divergences  # sí hay divergence pero no bloquea


# ── render_open_directive ───────────────────────────────────────────────

class TestRenderDirective:
    def _matched_record(self, account_number, **overrides):
        plan_row = next(r for r in SUPABASE_PLAN_FIXTURE
                        if r["account_number"] == account_number)
        laudus_row = next(a for a in LAUDUS_FIXTURE
                          if a["accountNumber"].ljust(6, "0") == account_number)
        record = {
            "account_number": account_number,
            "laudus_original_length": len(laudus_row["accountNumber"]),
            "laudus_account_id": laudus_row["accountId"],
            "laudus_name": laudus_row["name"],
            "supabase_name": plan_row["account_name"],
            "cat1": plan_row["cat1"], "cat2": plan_row["cat2"], "cat3": plan_row["cat3"],
            "supabase_active": True,
        }
        record.update(overrides)
        return record

    def test_non_bank_expense(self):
        rec = self._matched_record("413044")
        text = render_open_directive(rec, bank_meta=None)
        assert "2020-12-31 open Expenses:EAG:CombustibleVehculos-413044 CLP" in text
        assert 'code: "413044"' in text
        assert 'laudus_categoria1: "GASTOS - EGRESOS"' in text
        assert "bank_account_id" not in text

    def test_bank_cta_corriente_clp(self):
        rec = self._matched_record("111005")
        bank = next(b for b in SUPABASE_BANKS_FIXTURE if b["account_number"] == "111005")
        text = render_open_directive(rec, bank_meta=bank)
        assert "Assets:EAG:Bancos:BancoBci10160175-111005 CLP" in text
        assert 'bank_account_id: "uuid-bci-001"' in text
        assert 'bank_name: "BCI"' in text
        assert 'bank_account_type: "cta_corriente"' in text
        assert 'bank_account_currency: "CLP"' in text

    def test_bank_tarjeta_credito_usd_uses_dual_commodity(self):
        rec = self._matched_record("215001")
        bank = next(b for b in SUPABASE_BANKS_FIXTURE if b["account_number"] == "215001")
        text = render_open_directive(rec, bank_meta=bank)
        # Q7: TC va a Liabilities aún si cat1 dice ACTIVO EAG.
        # En este fixture cat1=PASIVO, así que Liabilities por ambos lados.
        assert "Liabilities:EAG:TC:VisaInfinityEduardo-215001 CLP, USD" in text
        assert 'bank_account_currency: "USD"' in text

    def test_escapes_double_quotes_in_name(self):
        rec = self._matched_record("111005",
                                   laudus_name='Banco "VIP" BCI')
        text = render_open_directive(rec, bank_meta=None)
        assert 'laudus_account_name: "Banco \\"VIP\\" BCI"' in text


# ── render_accounts_beancount ───────────────────────────────────────────

class TestRenderAccounts:
    def test_renders_sorted_with_header(self):
        cc = crosscheck(LAUDUS_FIXTURE, SUPABASE_PLAN_FIXTURE)
        leaves = [r for r in cc.matched if r["laudus_original_length"] == 6]
        bank_index = index_bank_accounts(SUPABASE_BANKS_FIXTURE)
        text = render_accounts_beancount(leaves, bank_index)
        assert text.startswith(";; ledger/accounts.beancount")
        # Order: 111005 < 215001 < 413044
        i_111 = text.index("-111005")
        i_215 = text.index("-215001")
        i_413 = text.index("-413044")
        assert i_111 < i_215 < i_413


# ── run_bootstrap end-to-end with fixtures ──────────────────────────────

class TestRunBootstrap:
    def test_happy_path_writes_accounts_and_reports(self, tmp_path):
        ledger = tmp_path / "ledger"
        reports = tmp_path / "bootstrap"
        ledger.mkdir()
        rc = run_bootstrap(
            ledger_path=ledger, reports_path=reports,
            laudus_accounts=LAUDUS_FIXTURE,
            supabase_plan=SUPABASE_PLAN_FIXTURE,
            supabase_banks=SUPABASE_BANKS_FIXTURE,
        )
        assert rc == 0
        out = (ledger / "accounts.beancount").read_text(encoding="utf-8")
        assert "Assets:EAG:Bancos:BancoBci10160175-111005" in out
        assert "Liabilities:EAG:TC:VisaInfinityEduardo-215001" in out
        assert "Expenses:EAG:CombustibleVehculos-413044" in out
        # 3 hierarchy nodes capturados aparte
        with (reports / "report-hierarchy-nodes.csv").open(encoding="utf-8") as fp:
            rows = list(csv.DictReader(fp))
        assert len(rows) == 3
        assert {r["account_number"] for r in rows} == {"100000", "110000", "111000"}

    def test_mismatch_blocks_render(self, tmp_path):
        ledger = tmp_path / "ledger"
        reports = tmp_path / "bootstrap"
        ledger.mkdir()
        rc = run_bootstrap(
            ledger_path=ledger, reports_path=reports,
            laudus_accounts=LAUDUS_FIXTURE,
            supabase_plan=SUPABASE_PLAN_FIXTURE[:-1],  # falta 413044
            supabase_banks=SUPABASE_BANKS_FIXTURE,
        )
        assert rc == 2
        # accounts.beancount NO se escribe
        assert not (ledger / "accounts.beancount").exists()
        # report-mismatch-accounts.csv contiene la línea laudus-only
        with (reports / "report-mismatch-accounts.csv").open(encoding="utf-8") as fp:
            rows = list(csv.DictReader(fp))
        assert any(r["source"] == "laudus-only" and r["account_number"] == "413044" for r in rows)

    def test_unmapped_categoria1_blocks_render(self, tmp_path):
        ledger = tmp_path / "ledger"
        reports = tmp_path / "bootstrap"
        ledger.mkdir()
        bad_supabase = [
            {**r, "cat1": "CUENTA DE ORDEN"} if r["account_number"] == "413044" else r
            for r in SUPABASE_PLAN_FIXTURE
        ]
        rc = run_bootstrap(
            ledger_path=ledger, reports_path=reports,
            laudus_accounts=LAUDUS_FIXTURE,
            supabase_plan=bad_supabase,
            supabase_banks=SUPABASE_BANKS_FIXTURE,
        )
        assert rc == 2
        assert not (ledger / "accounts.beancount").exists()
        with (reports / "report-unmapped-accounts.csv").open(encoding="utf-8") as fp:
            rows = list(csv.DictReader(fp))
        assert any(r["account_number"] == "413044" for r in rows)
