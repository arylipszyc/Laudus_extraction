"""Tests for BeancountWriter — Story 9.4 AC1/AC2/AC6."""
from decimal import Decimal

from beancount import loader

from pipeline.writers.beancount_writer import (
    JournalEntry,
    load_account_index,
    write_jes,
)

# Mini accounts file: two known codes (111005 Asset, 411005 Income).
MINI_ACCOUNTS = """\
2020-12-31 open Assets:EAG:Bancos:BancoBci-111005 CLP
  code: "111005"
  laudus_account_name: "Banco BCI"
2020-12-31 open Income:EAG:Ventas-411005 CLP
  code: "411005"
  laudus_account_name: "Ventas"
"""


def _row(je_id, line, code, debit=0, credit=0, date="2024-03-15", desc="Pago", num=1001):
    return {
        "journalentryid": je_id, "journalentrynumber": num, "date": date,
        "accountnumber": code, "lineid": line, "description": desc,
        "debit": debit, "credit": credit, "currencycode": "CLP",
        "paritytomaincurrency": 1.0, "periodo": "2024-03-31",
    }


def _setup(tmp_path, accounts=MINI_ACCOUNTS):
    accounts_path = tmp_path / "accounts.beancount"
    accounts_path.write_text(accounts, encoding="utf-8")
    target_dir = tmp_path / "imports" / "laudus"
    pending_path = tmp_path / "imports" / "_new-accounts-pending.beancount"
    return accounts_path, target_dir, pending_path


# A balanced JE: debit 100000 to bank, credit 100000 to income.
def _balanced_je(je_id=12345, date="2024-03-15"):
    return [
        _row(je_id, 1, "111005", debit=100000, date=date),
        _row(je_id, 2, "411005", credit=100000, date=date),
    ]


# ── AC1: directive shape, metadata, sign, CLP ────────────────────────────────


def test_writes_month_file_with_metadata(tmp_path):
    accounts_path, target_dir, pending_path = _setup(tmp_path)
    result = write_jes(_balanced_je(), target_dir, accounts_path, pending_path)
    content = (target_dir / "2024-03.beancount").read_text(encoding="utf-8")
    assert 'id: "12345"' in content
    assert 'je_num: "1001"' in content
    assert 'source: "laudus-erp"' in content
    assert "Assets:EAG:Bancos:BancoBci-111005  100000.00 CLP" in content
    assert "Income:EAG:Ventas-411005  -100000.00 CLP" in content
    assert result.jes_added == 1


def test_groups_one_file_per_month(tmp_path):
    accounts_path, target_dir, pending_path = _setup(tmp_path)
    rows = _balanced_je(1, "2024-03-15") + _balanced_je(2, "2024-06-20")
    write_jes(rows, target_dir, accounts_path, pending_path)
    assert (target_dir / "2024-03.beancount").exists()
    assert (target_dir / "2024-06.beancount").exists()


def test_output_loads_without_errors(tmp_path):
    """AC1/AC7: generated directives pass bean-check (loader has no errors)."""
    accounts_path, target_dir, pending_path = _setup(tmp_path)
    write_jes(_balanced_je(), target_dir, accounts_path, pending_path)
    main = tmp_path / "main.beancount"
    main.write_text(
        'option "operating_currency" "CLP"\n'
        '1900-01-01 commodity CLP\n'
        'include "accounts.beancount"\n'
        'include "imports/laudus/2024-03.beancount"\n'
        'include "imports/_new-accounts-pending.beancount"\n',
        encoding="utf-8",
    )
    _entries, errors, _options = loader.load_file(str(main))
    assert errors == []


# ── AC1: journalEntryId == 0 filter ──────────────────────────────────────────


def test_drops_journal_entry_id_zero(tmp_path):
    accounts_path, target_dir, pending_path = _setup(tmp_path)
    rows = _balanced_je() + [
        _row(0, 1, "111005", debit=999, date="2024-03-15"),
        _row(0, 2, "411005", credit=999, date="2024-03-15"),
    ]
    result = write_jes(rows, target_dir, accounts_path, pending_path)
    content = (target_dir / "2024-03.beancount").read_text(encoding="utf-8")
    assert "999" not in content
    assert result.jes_added == 1  # only the id=12345 JE


# ── AC2: idempotency ─────────────────────────────────────────────────────────


def test_idempotent_bit_identical(tmp_path):
    accounts_path, target_dir, pending_path = _setup(tmp_path)
    rows = _balanced_je(1, "2024-03-15") + _balanced_je(2, "2024-06-20")
    write_jes(rows, target_dir, accounts_path, pending_path)
    first = {p.name: p.read_text(encoding="utf-8") for p in target_dir.glob("*.beancount")}
    write_jes(rows, target_dir, accounts_path, pending_path)  # second run, same input
    second = {p.name: p.read_text(encoding="utf-8") for p in target_dir.glob("*.beancount")}
    assert first == second


def test_second_run_reports_dedup(tmp_path):
    accounts_path, target_dir, pending_path = _setup(tmp_path)
    rows = _balanced_je()
    write_jes(rows, target_dir, accounts_path, pending_path)
    result = write_jes(rows, target_dir, accounts_path, pending_path)
    assert result.jes_added == 0
    assert result.jes_dedup == 1


# ── AC2: incremental merge preserves prior data ──────────────────────────────


def test_incremental_merge_preserves_existing(tmp_path):
    accounts_path, target_dir, pending_path = _setup(tmp_path)
    write_jes(_balanced_je(1, "2024-03-15"), target_dir, accounts_path, pending_path)
    # New JE in the SAME month — must not drop JE 1.
    write_jes(_balanced_je(2, "2024-03-20"), target_dir, accounts_path, pending_path)
    content = (target_dir / "2024-03.beancount").read_text(encoding="utf-8")
    assert 'id: "1"' in content
    assert 'id: "2"' in content


def test_incremental_je_moved_to_new_month_leaves_no_stale_duplicate(tmp_path):
    """AC2: a JE re-fetched with a corrected date that moves it to another month must
    not remain in its original month. The now-empty old month file is removed so the
    JE appears exactly once across all files."""
    accounts_path, target_dir, pending_path = _setup(tmp_path)
    write_jes(_balanced_je(1, "2024-03-15"), target_dir, accounts_path, pending_path)
    assert (target_dir / "2024-03.beancount").exists()
    # Same id, corrected date → moves from 2024-03 to 2024-06.
    write_jes(_balanced_je(1, "2024-06-15"), target_dir, accounts_path, pending_path)
    assert not (target_dir / "2024-03.beancount").exists()  # old month removed
    all_content = "".join(p.read_text(encoding="utf-8") for p in target_dir.glob("*.beancount"))
    assert all_content.count('id: "1"') == 1  # exactly once, no stale duplicate


def test_backfill_replace_regenerates_from_rows(tmp_path):
    accounts_path, target_dir, pending_path = _setup(tmp_path)
    write_jes(_balanced_je(1, "2024-03-15"), target_dir, accounts_path, pending_path)
    # replace=True ignores existing → JE 1 gone, only JE 2.
    write_jes(_balanced_je(2, "2024-03-20"), target_dir, accounts_path, pending_path, replace=True)
    content = (target_dir / "2024-03.beancount").read_text(encoding="utf-8")
    assert 'id: "1"' not in content
    assert 'id: "2"' in content


# ── AC6: new accounts → pending file + #pending-account tag ───────────────────


def test_unknown_account_goes_to_pending(tmp_path):
    accounts_path, target_dir, pending_path = _setup(tmp_path)
    # code 999999 is NOT in MINI_ACCOUNTS.
    rows = [
        _row(50, 1, "111005", debit=5000, date="2024-05-10"),
        _row(50, 2, "999999", credit=5000, date="2024-05-10"),
    ]
    result = write_jes(rows, target_dir, accounts_path, pending_path)
    month = (target_dir / "2024-05.beancount").read_text(encoding="utf-8")
    pending = pending_path.read_text(encoding="utf-8")
    assert "#pending-account" in month
    assert "Assets:EAG:PendingReview:Cuenta-999999" in month
    assert 'open Assets:EAG:PendingReview:Cuenta-999999 CLP' in pending
    assert 'code: "999999"' in pending
    assert result.pending_accounts == 1


def test_pending_self_cleans_when_account_promoted(tmp_path):
    accounts_path, target_dir, pending_path = _setup(tmp_path)
    rows = [
        _row(50, 1, "111005", debit=5000, date="2024-05-10"),
        _row(50, 2, "999999", credit=5000, date="2024-05-10"),
    ]
    write_jes(rows, target_dir, accounts_path, pending_path)
    assert "999999" in pending_path.read_text(encoding="utf-8")
    # Promote 999999 into accounts.beancount, re-run → drops from pending.
    accounts_path.write_text(
        MINI_ACCOUNTS + '2020-12-31 open Liabilities:EAG:Tarjeta-999999 CLP\n  code: "999999"\n',
        encoding="utf-8",
    )
    write_jes(rows, target_dir, accounts_path, pending_path, replace=True)
    assert 'open Assets:EAG:PendingReview:Cuenta-999999' not in pending_path.read_text(encoding="utf-8")


# ── load_account_index ───────────────────────────────────────────────────────


def test_load_account_index(tmp_path):
    accounts_path, _, _ = _setup(tmp_path)
    index = load_account_index(accounts_path)
    assert index["111005"] == "Assets:EAG:Bancos:BancoBci-111005"
    assert index["411005"] == "Income:EAG:Ventas-411005"


# ── Story 12.2: índice con noción de entidad + cuarentena por libro (FR51) ────

# Árbol multi-libro: 111005 existe en AMBOS libros como cuenta DISTINTA (colisión
# real del intake §4); un namespace legacy sin entidad pertenece a EAG.
MULTI_BOOK_ACCOUNTS = MINI_ACCOUNTS + """\
2020-12-31 open Assets:FFCC:CajaFfcc-111005 CLP
  code: "111005"
2020-12-31 open Expenses:JAB:GastosPersonales-811001 CLP
  code: "811001"
2020-12-31 open Equity:Apertura:Legacy CLP
  code: "900001"
"""


def _books():
    from pipeline.config.laudus_config import get_book
    return get_book("EAG"), get_book("RUT2")


def test_load_account_index_scoped_por_libro(tmp_path):
    """El mismo code (111005) resuelve a la cuenta DEL LIBRO — nunca a la homónima
    del otro. El namespace legacy sin entidad (Equity:Apertura) es de EAG."""
    eag, rut2 = _books()
    accounts_path, _, _ = _setup(tmp_path, accounts=MULTI_BOOK_ACCOUNTS)

    idx_eag = load_account_index(accounts_path, eag)
    assert idx_eag["111005"] == "Assets:EAG:Bancos:BancoBci-111005"
    assert "811001" not in idx_eag                       # JAB fuera del libro EAG
    assert idx_eag["900001"] == "Equity:Apertura:Legacy"  # legacy sin entidad → EAG

    idx_rut2 = load_account_index(accounts_path, rut2)
    assert idx_rut2["111005"] == "Assets:FFCC:CajaFfcc-111005"
    assert idx_rut2["811001"] == "Expenses:JAB:GastosPersonales-811001"
    assert "411005" not in idx_rut2                      # cuenta EAG fuera de RUT2
    assert "900001" not in idx_rut2                      # legacy sin entidad NO es RUT2


def test_load_account_index_sin_libro_conserva_comportamiento_legacy(tmp_path):
    accounts_path, _, _ = _setup(tmp_path, accounts=MULTI_BOOK_ACCOUNTS)
    index = load_account_index(accounts_path)
    assert len(index) == 4  # todos los codes; 111005 colisionado (last-wins, pre-12.2)


def test_write_jes_rut2_cuarentena_por_entidad_del_libro(tmp_path):
    """AC2: code desconocido en corrida RUT2 → Assets:{FFCC|JAB}:PendingReview según
    dígito de raíz, y el header del pending file nombra el archivo del libro."""
    _, rut2 = _books()
    accounts_path, _, _ = _setup(tmp_path, accounts=MULTI_BOOK_ACCOUNTS)
    target_dir = tmp_path / "imports" / "laudus-rut2"
    pending_path = tmp_path / "imports" / "_new-accounts-pending-rut2.beancount"
    rows = [
        _row(70, 1, "111005", debit=5000, date="2024-05-10"),
        _row(70, 2, "433015", credit=3000, date="2024-05-10"),   # raíz 4 → FFCC
        _row(70, 3, "871005", credit=2000, date="2024-05-10"),   # raíz 8 → JAB
    ]
    result = write_jes(rows, target_dir, accounts_path, pending_path, book=rut2)
    month = (target_dir / "2024-05.beancount").read_text(encoding="utf-8")
    assert "Assets:FFCC:CajaFfcc-111005" in month
    assert "Assets:FFCC:PendingReview:Cuenta-433015" in month
    assert "Assets:JAB:PendingReview:Cuenta-871005" in month
    assert "EAG" not in month
    pending = pending_path.read_text(encoding="utf-8")
    assert pending.startswith(";; ledger/imports/_new-accounts-pending-rut2.beancount\n")
    assert "open Assets:FFCC:PendingReview:Cuenta-433015 CLP" in pending
    assert "open Assets:JAB:PendingReview:Cuenta-871005 CLP" in pending
    assert result.pending_accounts == 2


def test_write_jes_libro_eag_byte_identico_al_legacy(tmp_path):
    """AC4 (anti-regresión): una corrida EAG con book explícito produce archivos
    BYTE-IDÉNTICOS a los del comportamiento pre-12.2 (book=None), incluida la
    cuarentena EAG y el pending file."""
    eag, _ = _books()
    rows = _balanced_je() + [
        _row(60, 1, "111005", debit=5000, date="2024-05-10"),
        _row(60, 2, "999999", credit=5000, date="2024-05-10"),  # desconocido → cuarentena
    ]

    legacy_dir = tmp_path / "legacy"
    a1 = legacy_dir / "accounts.beancount"
    legacy_dir.mkdir()
    a1.write_text(MINI_ACCOUNTS, encoding="utf-8")
    write_jes(rows, legacy_dir / "imports" / "laudus", a1,
              legacy_dir / "imports" / "_new-accounts-pending.beancount")

    book_dir = tmp_path / "book"
    a2 = book_dir / "accounts.beancount"
    book_dir.mkdir()
    a2.write_text(MINI_ACCOUNTS, encoding="utf-8")
    write_jes(rows, book_dir / "imports" / "laudus", a2,
              book_dir / "imports" / "_new-accounts-pending.beancount", book=eag)

    legacy_files = sorted((legacy_dir / "imports").rglob("*.beancount"))
    book_files = sorted((book_dir / "imports").rglob("*.beancount"))
    assert [p.name for p in legacy_files] == [p.name for p in book_files]
    for lf, bf in zip(legacy_files, book_files):
        assert lf.read_bytes() == bf.read_bytes(), f"{lf.name} difiere entre legacy y book=EAG"
