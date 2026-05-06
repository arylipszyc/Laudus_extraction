"""Smoke runner — Story 9.5 end-to-end with a real PDF.

Usage:
    python -m bootstrap.smoke_cartola_upload samples/bci-visa-202604.pdf BCI 1234

Bypasses the MISSING_LAST4 gate (production endpoint will reject) by passing
a synthetic BankAccountEntry — useful before Story 9.3 AC8 has Ary populate
last4 metadata via Fava.

The pipeline exercised: PDF bytes >GeminiClient.extract_pdf >schema validation
>post-process warnings >write to staging_dir. Prints a summary on success.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# .env loading — preserve existing dev experience.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from backend.app.api.v1.cartolas.service import (
    new_batch_id,
    process_upload_sync,
)
from backend.app.integrations.bank_account_index import BankAccountEntry
from backend.app.integrations.gemini_client import GeminiClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for cartola upload")
    parser.add_argument("pdf_path", type=Path, help="Path to the PDF cartola")
    parser.add_argument("bank_name", help="e.g. BCI, Santander")
    parser.add_argument("last4", help="Last 4 digits of the card/account")
    parser.add_argument(
        "--account-type",
        default="tarjeta_credito",
        choices=["tarjeta_credito", "cta_corriente", "cta_vista", "cta_ahorro", "linea_credito"],
    )
    parser.add_argument("--currency", default="CLP", choices=["CLP", "USD", "EUR"])
    parser.add_argument(
        "--staging-dir",
        type=Path,
        default=Path("ledger/imports/cartolas/_staging"),
    )
    args = parser.parse_args()

    if not args.pdf_path.exists():
        print(f"ERROR: PDF not found at {args.pdf_path}", file=sys.stderr)
        return 1

    pdf_bytes = args.pdf_path.read_bytes()
    print(f">PDF: {args.pdf_path} ({len(pdf_bytes)} bytes)")

    entry = BankAccountEntry(
        bank_account_id=f"smoke-{args.bank_name.lower()}-{args.last4}",
        bank_name=args.bank_name,
        account_label=f"{args.bank_name} {args.account_type} {args.last4} (smoke)",
        account_type=args.account_type,
        entity="EAG",
        currency=args.currency,
        last4=args.last4,
        beancount_account=f"Liabilities:EAG:TC:Smoke-{args.last4}",
    )

    print(f">BankAccountEntry: {entry.account_label}")
    print(f">Calling Gemini ({GeminiClient().model})…")

    gemini = GeminiClient()
    batch_id = new_batch_id()
    args.staging_dir.mkdir(parents=True, exist_ok=True)

    canonical = process_upload_sync(
        batch_id=batch_id,
        pdf_bytes=pdf_bytes,
        bank_account_entry=entry,
        gemini=gemini,
        staging_dir=args.staging_dir,
    )

    print()
    print(f"[ok]batch_id: {batch_id}")
    print(f"[ok]schema_version: {canonical.schema_version}")
    print(f"[ok]period: {canonical.period.start} >{canonical.period.end}")
    print(f"[ok]currency: {canonical.currency}")
    print(f"[ok]balances: opening={canonical.balances.opening} closing={canonical.balances.closing}")
    print(f"[ok]transactions: {len(canonical.transactions)}")
    print(f"[ok]warnings: {len(canonical.extraction.warnings)}")
    for w in canonical.extraction.warnings:
        line = f" line={w.line_no}" if w.line_no else ""
        print(f"    - {w.code}{line}: {w.detail}")
    print(f"[ok]staging file: {args.staging_dir}/{batch_id}.cartola.json")

    if canonical.transactions:
        print()
        print("Sample transactions (first 3):")
        for tx in canonical.transactions[:3]:
            print(f"    {tx.line_no:3} {tx.date} {tx.amount:>12} {tx.currency}  {tx.description[:60]}")

    csv_path = args.staging_dir / f"{batch_id}.transactions.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "line_no", "date", "description", "amount", "currency",
            "merchant_country", "operation_type",
        ])
        for tx in canonical.transactions:
            raw = tx.raw or {}
            writer.writerow([
                tx.line_no, tx.date, tx.description, tx.amount, tx.currency,
                raw.get("merchant_country", ""), raw.get("operation_type", ""),
            ])
    print(f"[ok]csv: {csv_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
