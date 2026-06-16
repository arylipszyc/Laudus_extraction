"""BeancountWriter — convierte JEs Laudus normalizadas en directivas Beancount.

Story 9.4 AC1/AC2/AC6. Reglas clave:

- **CLP-only** (Q4): Laudus no preserva el USD original; toda JE se emite en CLP.
- **Mapeo de cuenta** vía `code:` metadata de `accounts.beancount` (parseado y
  cacheado en memoria). NO se re-deriva la clasificación Categoria1→root.
- **Filtro defensivo** `journalEntryId == 0` (saldos sintéticos "Saldo anterior").
- **Idempotencia** (AC2): se reconcilia con lo ya escrito (merge por `id:`) y se
  regeneran los archivos `YYYY-MM.beancount` de forma determinista → corridas con el
  mismo input producen archivos bit-idénticos.
- **Cuentas nuevas** (AC6): un `accountnumber` ausente de `accounts.beancount` NO se
  abre automáticamente; se emite un `open` tentativo en `_new-accounts-pending.beancount`
  (cuenta de cuarentena) y la JE que la referencia lleva `#pending-account`.

Una JE Laudus = varias filas (una por `lineId`); se agrupan por `journalentryid` en
una `Transaction` con una posting por línea (monto = debit − credit).
"""
from __future__ import annotations

import logging
import os
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from beancount.core.data import Open, Transaction
from beancount.parser import parser

logger = logging.getLogger(__name__)

_PENDING_OPEN_DATE = "2020-01-01"
_PENDING_HEADER = (
    ";; ledger/imports/_new-accounts-pending.beancount\n"
    ";;\n"
    ";; Cuentas detectadas por el importer Laudus (Story 9.4) que NO existen\n"
    ";; todavía en accounts.beancount. Cada entrada es un `open` tentativo +\n"
    ";; sus JEs llevan tag #pending-account hasta que Ary las promueva\n"
    ";; manualmente al accounts.beancount con su Cat1/2/3 + bank metadata.\n"
    ";; Generado automáticamente — no editar a mano (se regenera en cada corrida).\n"
)


@dataclass
class JournalEntry:
    """Una JE normalizada lista para emitir como Transaction Beancount."""
    date: str                      # ISO YYYY-MM-DD
    id: str                        # journalentryid
    je_num: str                    # journalentrynumber
    narration: str
    postings: list[tuple[str, Decimal]] = field(default_factory=list)  # (account, amount)
    pending: bool = False          # alguna cuenta es de cuarentena → #pending-account


@dataclass
class WriteResult:
    jes_added: int = 0
    jes_dedup: int = 0
    pending_accounts: int = 0
    months_written: list[str] = field(default_factory=list)


# ── Account index (code → beancount account) ────────────────────────────────


def load_account_index(accounts_path: str | os.PathLike) -> dict[str, str]:
    """Map `code` metadata → full Beancount account name from accounts.beancount."""
    entries, _errors, _options = parser.parse_file(str(accounts_path))
    index: dict[str, str] = {}
    for e in entries:
        if isinstance(e, Open):
            code = (e.meta or {}).get("code")
            if code is not None:
                index[str(code)] = e.account
    return index


def _pending_account(code: str) -> str:
    """Quarantine account for an unknown Laudus code (reclassified manually)."""
    return f"Assets:EAG:PendingReview:Cuenta-{code}"


# ── Formatting (deterministic → idempotent) ─────────────────────────────────


def _fmt_amount(number: Decimal) -> str:
    return f"{number.quantize(Decimal('0.01'))} CLP"


def _escape(text: str) -> str:
    """Escape a narration for a Beancount string literal (one line)."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()


def _format_je(je: JournalEntry) -> str:
    tag = " #pending-account" if je.pending else ""
    lines = [f'{je.date} * "{_escape(je.narration)}"{tag}']
    lines.append(f'  id: "{je.id}"')
    lines.append(f'  je_num: "{je.je_num}"')
    lines.append('  source: "laudus-erp"')
    for account, amount in je.postings:
        lines.append(f"  {account}  {_fmt_amount(amount)}")
    return "\n".join(lines)


def _month_of(iso_date: str) -> str:
    return iso_date[:7]  # YYYY-MM


# ── Build JEs from raw Laudus rows ──────────────────────────────────────────


def _rows_to_jes(rows: list[dict], account_index: dict[str, str]) -> tuple[dict[str, JournalEntry], set[str]]:
    """Group normalized ledger rows by journalentryid → JournalEntry.

    Drops rows with journalentryid == 0 (synthetic "Saldo anterior"). Returns
    (jes_by_id, pending_codes_seen).
    """
    jes: "OrderedDict[str, JournalEntry]" = OrderedDict()
    pending_codes: set[str] = set()
    for row in rows:
        je_id = row.get("journalentryid")
        if je_id in (0, "0", None):
            continue
        je_id = str(je_id)
        code = str(row.get("accountnumber", ""))
        account = account_index.get(code)
        is_pending = account is None
        if is_pending:
            account = _pending_account(code)
            pending_codes.add(code)
        amount = Decimal(str(row.get("debit", 0))) - Decimal(str(row.get("credit", 0)))
        if je_id not in jes:
            jes[je_id] = JournalEntry(
                date=str(row.get("date", ""))[:10],
                id=je_id,
                je_num=str(row.get("journalentrynumber", "")),
                narration=str(row.get("description", "") or ""),
                postings=[],
            )
        je = jes[je_id]
        if not je.narration and row.get("description"):
            je.narration = str(row["description"])
        je.postings.append((account, amount))
        if is_pending:
            je.pending = True
    return jes, pending_codes


def _parse_existing_jes(target_dir: Path) -> dict[str, JournalEntry]:
    """Recover already-written Laudus JEs (source=="laudus-erp") from month files."""
    jes: dict[str, JournalEntry] = {}
    if not target_dir.is_dir():
        return jes
    for path in target_dir.glob("*.beancount"):
        if path.name.startswith("_"):
            continue
        entries, _errors, _options = parser.parse_file(str(path))
        for e in entries:
            if not isinstance(e, Transaction):
                continue
            meta = e.meta or {}
            if meta.get("source") != "laudus-erp":
                continue
            je_id = str(meta.get("id", ""))
            postings = [
                (p.account, p.units.number)
                for p in e.postings
                if p.units is not None and p.units.number is not None
            ]
            jes[je_id] = JournalEntry(
                date=e.date.isoformat(),
                id=je_id,
                je_num=str(meta.get("je_num", "")),
                narration=e.narration or "",
                postings=postings,
                pending="pending-account" in (e.tags or frozenset()),
            )
    return jes


# ── Pending-accounts file ───────────────────────────────────────────────────


def _existing_pending_codes(pending_path: Path) -> set[str]:
    if not pending_path.exists():
        return set()
    entries, _errors, _options = parser.parse_file(str(pending_path))
    return {
        str((e.meta or {}).get("code"))
        for e in entries
        if isinstance(e, Open) and (e.meta or {}).get("code") is not None
    }


def _write_pending_file(pending_path: Path, codes: set[str]) -> None:
    """Regenerate the pending-accounts file deterministically (sorted by code)."""
    chunks = [_PENDING_HEADER]
    for code in sorted(codes):
        chunks.append(
            f"\n{_PENDING_OPEN_DATE} open {_pending_account(code)} CLP\n"
            f'  code: "{code}"\n'
            f'  pending_review: "TRUE"\n'
        )
    content = "".join(chunks)
    if not content.endswith("\n"):
        content += "\n"
    pending_path.write_text(content, encoding="utf-8")


# ── Public entry point ──────────────────────────────────────────────────────


def write_jes(
    rows: list[dict],
    target_dir: str | os.PathLike,
    accounts_path: str | os.PathLike,
    pending_path: str | os.PathLike,
    replace: bool = False,
) -> WriteResult:
    """Emit `imports/laudus/YYYY-MM.beancount` from normalized Laudus rows.

    Args:
        rows: normalized ledger rows (output of `map_ledger_row`).
        target_dir: `ledger/imports/laudus/`.
        accounts_path: `ledger/accounts.beancount` (account code index).
        pending_path: `ledger/imports/_new-accounts-pending.beancount`.
        replace: True (backfill) regenerates from `rows` only; False (incremental)
            merges with already-written JEs by `id` (new overrides existing).
    """
    target_dir = Path(target_dir)
    pending_path = Path(pending_path)
    target_dir.mkdir(parents=True, exist_ok=True)

    account_index = load_account_index(accounts_path)
    new_jes, pending_codes = _rows_to_jes(rows, account_index)

    existing_jes = {} if replace else _parse_existing_jes(target_dir)
    existing_ids = set(existing_jes.keys())

    merged: dict[str, JournalEntry] = dict(existing_jes)
    merged.update(new_jes)  # new overrides existing (corrections + idempotency)

    # Group by month and regenerate each month file deterministically.
    by_month: dict[str, list[JournalEntry]] = {}
    for je in merged.values():
        by_month.setdefault(_month_of(je.date), []).append(je)

    months_written = []
    for month, jes in sorted(by_month.items()):
        jes.sort(key=lambda j: (j.date, j.id))
        body = "\n\n".join(_format_je(j) for j in jes)
        (target_dir / f"{month}.beancount").write_text(body + "\n", encoding="utf-8")
        months_written.append(month)

    # A merged JE whose date moved to another month (correction) can leave its
    # original month with zero JEs. That month is no longer in `by_month`, so its
    # file was not regenerated above and still holds the stale JE — a duplicate.
    # Remove any previously-occupied month that no longer holds a JE (glob include
    # tolerates the missing file). Scoped to `existing_jes`, so backfill — which
    # has none — never deletes out-of-range months.
    emptied_months = {_month_of(je.date) for je in existing_jes.values()} - set(by_month)
    for month in emptied_months:
        (target_dir / f"{month}.beancount").unlink(missing_ok=True)

    # Reconcile the pending-accounts file: keep codes still unknown + new ones.
    surviving_pending = {c for c in _existing_pending_codes(pending_path) if c not in account_index}
    all_pending = surviving_pending | pending_codes
    _write_pending_file(pending_path, all_pending)

    new_ids = set(new_jes.keys())
    return WriteResult(
        jes_added=len(new_ids - existing_ids),
        jes_dedup=len(new_ids & existing_ids),
        pending_accounts=len(pending_codes),
        months_written=months_written,
    )
