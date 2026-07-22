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

from pipeline.config.laudus_config import ALL_BOOK_ENTITIES, BookConfig

logger = logging.getLogger(__name__)

_PENDING_OPEN_DATE = "2020-01-01"
_LEGACY_PENDING_FILE = "_new-accounts-pending.beancount"  # book=None (callers pre-12.2)
_PENDING_HEADER_TEMPLATE = (
    ";; ledger/imports/{pending_file}\n"
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
    # (account, amount, desc) — `desc` = glosa POR LÍNEA de Laudus (Laudus da una por
    # lineId; NO hay glosa de cabecera). La narration del asiento es neutra `JE <num>`;
    # cada pata lleva su propia glosa en metadata `desc:`, para que la reportería lea el
    # concepto real de cada línea y no confunda con la de otra pata del mismo comprobante.
    postings: list[tuple[str, Decimal, str]] = field(default_factory=list)
    pending: bool = False          # alguna cuenta es de cuarentena → #pending-account
    entity: str | None = None      # libro de origen (book_id: "EAG" | "RUT2") → metadata `entity:`


@dataclass
class WriteResult:
    jes_added: int = 0
    jes_dedup: int = 0
    pending_accounts: int = 0
    months_written: list[str] = field(default_factory=list)


# ── Account index (code → beancount account) ────────────────────────────────


def _account_in_book(account: str, book: BookConfig) -> bool:
    """¿La cuenta pertenece al libro? Autoridad = 2º segmento del path (entidad).

    Un 2º segmento que no es entidad de NINGÚN libro (namespaces legacy sin entidad,
    ej. `Equity:Apertura:*`) pertenece al libro con `include_entityless` (EAG).
    """
    parts = account.split(":")
    segment = parts[1] if len(parts) > 1 else ""
    if segment in book.entities:
        return True
    return book.include_entityless and segment not in ALL_BOOK_ENTITIES


def load_account_index(
    accounts_path: str | os.PathLike, book: BookConfig | None = None
) -> dict[str, str]:
    """Map `code` metadata → full Beancount account name from accounts.beancount.

    Con `book` el índice queda SCOPED al libro (Story 12.2 / FR51): solo entran las
    cuentas cuyo 2º segmento de path es una entidad del libro — un code de RUT2 que
    colisiona con uno de EAG nunca puede resolver a la cuenta homónima del otro
    libro. `book=None` = índice completo (callers legacy: bootstrap, tests).
    """
    entries, _errors, _options = parser.parse_file(str(accounts_path))
    index: dict[str, str] = {}
    for e in entries:
        if isinstance(e, Open):
            code = (e.meta or {}).get("code")
            if code is None:
                continue
            if book is not None and not _account_in_book(e.account, book):
                continue
            index[str(code)] = e.account
    return index


def _pending_account(code: str, book: BookConfig | None = None) -> str:
    """Quarantine account for an unknown Laudus code (reclassified manually).

    La entidad de cuarentena es la del LIBRO (12.2 AC2): EAG → `Assets:EAG:...`
    (idéntico al comportamiento previo); RUT2 → FFCC/JAB según dígito de raíz.
    """
    entity = book.pending_entity(code) if book is not None else "EAG"
    return f"Assets:{entity}:PendingReview:Cuenta-{code}"


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
    if je.entity:
        lines.append(f'  entity: "{je.entity}"')
    for account, amount, desc in je.postings:
        lines.append(f"  {account}  {_fmt_amount(amount)}")
        # Glosa POR LÍNEA de Laudus en CADA pata que la tenga. La narration del asiento
        # es neutra (`JE <num>`) y no describe ninguna pata: el concepto real de cada
        # línea vive acá. Sin `desc:` = la línea no traía glosa en Laudus.
        if desc:
            lines.append(f'    desc: "{_escape(desc)}"')
    return "\n".join(lines)


def _month_of(iso_date: str) -> str:
    return iso_date[:7]  # YYYY-MM


# ── Build JEs from raw Laudus rows ──────────────────────────────────────────


def _rows_to_jes(
    rows: list[dict], account_index: dict[str, str], book: BookConfig | None = None
) -> tuple[dict[str, JournalEntry], set[str]]:
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
            account = _pending_account(code, book)
            pending_codes.add(code)
        amount = Decimal(str(row.get("debit", 0))) - Decimal(str(row.get("credit", 0)))
        if je_id not in jes:
            je_num = str(row.get("journalentrynumber", ""))
            jes[je_id] = JournalEntry(
                date=str(row.get("date", ""))[:10],
                id=je_id,
                je_num=je_num,
                # Narration neutra: Laudus no tiene glosa de cabecera; usar la de la 1ª
                # línea (comportamiento previo) etiquetaba mal los comprobantes compuestos.
                narration=f"JE {je_num}".strip(),
                entity=book.book_id if book is not None else None,
                postings=[],
            )
        je = jes[je_id]
        je.postings.append((account, amount, str(row.get("description", "") or "")))
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
            # Glosa por-línea desde la metadata `desc:` (el writer la emite en cada pata
            # que la tenga; sin `desc:` = la línea no traía glosa en Laudus).
            postings = [
                (p.account, p.units.number, str((p.meta or {}).get("desc") or ""))
                for p in e.postings
                if p.units is not None and p.units.number is not None
            ]
            jes[je_id] = JournalEntry(
                date=e.date.isoformat(),
                id=je_id,
                je_num=str(meta.get("je_num", "")),
                narration=e.narration or "",
                entity=meta.get("entity"),
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


def _write_pending_file(pending_path: Path, codes: set[str], book: BookConfig | None = None) -> None:
    """Regenerate the pending-accounts file deterministically (sorted by code)."""
    pending_file = book.pending_file if book is not None else _LEGACY_PENDING_FILE
    chunks = [_PENDING_HEADER_TEMPLATE.format(pending_file=pending_file)]
    for code in sorted(codes):
        chunks.append(
            f"\n{_PENDING_OPEN_DATE} open {_pending_account(code, book)} CLP\n"
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
    existing_jes: dict[str, JournalEntry] | None = None,
    book: BookConfig | None = None,
) -> WriteResult:
    """Emit `imports/<subdir>/YYYY-MM.beancount` from normalized Laudus rows.

    Args:
        rows: normalized ledger rows (output of `map_ledger_row`).
        target_dir: `ledger/imports/laudus/` (o el subdir del libro).
        accounts_path: `ledger/accounts.beancount` (account code index).
        pending_path: `ledger/imports/_new-accounts-pending.beancount` (o el del libro).
        replace: True (backfill) regenerates from `rows` only; False (incremental)
            merges with already-written JEs by `id` (new overrides existing).
        existing_jes: JEs ya parseados por el caller (review 2026-07-06 D4b: el run
            incremental los parsea una vez para el from_date y los pasa acá — evita
            el segundo parse completo). None → se parsean acá (comportamiento previo).
            Ignorado con replace=True.
        book: libro Laudus (Story 12.2 / FR51). Scopea el índice de cuentas a las
            entidades del libro y deriva la entidad de cuarentena. `run_import` lo
            pasa SIEMPRE; None = comportamiento pre-12.2 (índice completo, cuarentena
            EAG) para callers/tests legacy.
    """
    target_dir = Path(target_dir)
    pending_path = Path(pending_path)
    target_dir.mkdir(parents=True, exist_ok=True)

    account_index = load_account_index(accounts_path, book)
    new_jes, pending_codes = _rows_to_jes(rows, account_index, book)

    if replace:
        existing_jes = {}
    elif existing_jes is None:
        existing_jes = _parse_existing_jes(target_dir)
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
    _write_pending_file(pending_path, all_pending, book)

    new_ids = set(new_jes.keys())
    return WriteResult(
        jes_added=len(new_ids - existing_ids),
        jes_dedup=len(new_ids & existing_ids),
        pending_accounts=len(pending_codes),
        months_written=months_written,
    )
