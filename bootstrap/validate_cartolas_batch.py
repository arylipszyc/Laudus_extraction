"""Batch validation runner for Gemini cartola extraction — Story 9.5c.

Wraps the Story 9.5 pipeline (`process_upload_sync`) so Ary can run the N PDFs
in `samples/` 3× each and read an aggregated markdown + CSV report instead of
validating PDF-by-PDF manually.

Usage:
    python -m bootstrap.validate_cartolas_batch samples/
    python -m bootstrap.validate_cartolas_batch samples/ --runs 3
    python -m bootstrap.validate_cartolas_batch samples/ \\
        --pdf samples/bci-visa-202604.pdf \\
        --override "estado-de-cuenta (21).pdf:Banco de Chile:1234" \\
        --keep-staging

Output: `_bmad-output/validation-runs/{YYYY-MM-DD-HHMMSS}/`
    report.md      — aggregated markdown
    runs.csv       — one row per run
    summary.csv    — one row per PDF
    staging/       — `.cartola.json` per run (deleted unless --keep-staging)

Read-only over Story 9.5: never touches `backend/`, `frontend/`, `ledger/`,
or the Gemini prompt. The metric is `% verde` over total PDFs; the script
reports it, the human decides dispatch 9.6a vs 9.5d.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import os
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

# Per-call timeout to prevent silent hangs in the SDK (observed 2026-05-19
# during 9-5f baseline: SDK call to Gemini stalled indefinitely, no error).
# Most calls take 30-60s; 180s is generous head-room.
PER_CALL_TIMEOUT_S = 180

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
from backend.app.integrations.cartola_post_process import (
    BALANCE_MISMATCH_TOLERANCE_CLP,
)
from backend.app.integrations.gemini_client import GeminiClient


ACCOUNT_TYPE_CHOICES = [
    "tarjeta_credito",
    "cta_corriente",
    "cta_vista",
    "cta_ahorro",
    "linea_credito",
]


class Color(str, Enum):
    VERDE = "verde"
    AMARILLO = "amarillo"
    ROJO = "rojo"

    @property
    def emoji(self) -> str:
        return {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}[self.value]


@dataclass
class RunResult:
    """One Gemini extraction attempt for one PDF.

    All numeric fields are None when `error` is set (extraction failed before
    producing a canonical).
    """
    pdf_filename: str
    run_idx: int
    bank_name: str
    n_transactions: int | None
    opening: Decimal | None
    closing: Decimal | None
    sum_amounts: Decimal | None
    balance_diff: Decimal | None
    warning_codes: list[str]
    n_positive: int | None
    n_negative: int | None
    n_zero: int | None
    error: str = ""


@dataclass
class PdfSummary:
    pdf_filename: str
    bank_name: str
    color: Color
    stable: bool
    drift_fields: list[str]
    warning_codes_distinct: list[str]
    runs: list[RunResult] = field(default_factory=list)
    notes: str = ""


# ── Filename → bank_name inference ───────────────────────────────────────


def infer_bank_from_filename(filename: str) -> str | None:
    """Convention `{banco}-{producto}-{YYYYMM}.pdf` from samples/README.md."""
    stem = filename.lower()
    if stem.startswith("banco-de-chile-") or stem.startswith("bdechile-"):
        return "Banco de Chile"
    if stem.startswith("bci-"):
        return "BCI"
    if stem.startswith("santander-"):
        return "Santander"
    return None


def parse_override(spec: str) -> tuple[str, str, str, str]:
    """`<pdf_filename>:<bank_name>:<last4>[:<currency>]` → (filename, bank, last4, currency).

    Filenames never contain `:`, bank names never contain `:` in practice.
    Currency is optional (default CLP) for backwards compat with the original
    3-field form. Closed enum: CLP | USD | EUR.
    """
    parts = spec.split(":", 3)
    if len(parts) not in (3, 4) or not all(p.strip() for p in parts):
        raise argparse.ArgumentTypeError(
            f"--override expects '<pdf_filename>:<bank_name>:<last4>[:<currency>]', got {spec!r}"
        )
    filename, bank, last4 = (parts[0].strip(), parts[1].strip(), parts[2].strip())
    currency = parts[3].strip().upper() if len(parts) == 4 else "CLP"
    if currency not in {"CLP", "USD", "EUR"}:
        raise argparse.ArgumentTypeError(
            f"--override currency must be CLP | USD | EUR, got {currency!r}"
        )
    return filename, bank, last4, currency


def resolve_pdf_metadata(
    pdf_path: Path,
    overrides: dict[str, tuple[str, str, str]],
) -> tuple[str, str, str, bool]:
    """Return (bank_name, last4, currency, used_fallback)."""
    name = pdf_path.name
    if name in overrides:
        bank, last4, currency = overrides[name]
        return bank, last4, currency, False
    inferred = infer_bank_from_filename(name)
    if inferred is not None:
        return inferred, "9999", "CLP", False
    return "Desconocido", "9999", "CLP", True


# ── Drift / classification ────────────────────────────────────────────────


def is_stable(runs: list[RunResult], tolerance: Decimal = BALANCE_MISMATCH_TOLERANCE_CLP) -> tuple[bool, list[str]]:
    """AC4: identical n_tx, opening, closing, warning codes; sum differs ≤ tolerance.

    Returns (stable, drift_fields). Errors short-circuit to unstable.
    """
    if any(r.error for r in runs):
        return False, ["error"]
    if len(runs) < 2:
        return True, []

    drift: list[str] = []
    n_tx_set = {r.n_transactions for r in runs}
    if len(n_tx_set) > 1:
        drift.append("n_transactions")

    opening_set = {r.opening for r in runs}
    if len(opening_set) > 1:
        drift.append("opening")

    closing_set = {r.closing for r in runs}
    if len(closing_set) > 1:
        drift.append("closing")

    sums = [r.sum_amounts for r in runs if r.sum_amounts is not None]
    if sums and (max(sums) - min(sums)) > tolerance:
        drift.append("sum_amounts")

    warning_sets = [tuple(sorted(r.warning_codes)) for r in runs]
    if len(set(warning_sets)) > 1:
        drift.append("warning_codes")

    return (len(drift) == 0), drift


def classify_pdf(runs: list[RunResult]) -> tuple[Color, bool, list[str]]:
    """AC5: ROJO → AMARILLO → VERDE priority order.

    Returns (color, stable, drift_fields).
    """
    # ROJO checks (any run triggers)
    if any(r.error for r in runs):
        return Color.ROJO, False, ["error"]
    if any("BALANCE_MISMATCH" in r.warning_codes for r in runs):
        # still compute stability for the report, but color is locked to ROJO
        stable, drift = is_stable(runs)
        return Color.ROJO, stable, drift
    if any(r.n_transactions == 0 for r in runs):
        stable, drift = is_stable(runs)
        return Color.ROJO, stable, drift

    stable, drift = is_stable(runs)

    # AMARILLO: drift OR any non-BALANCE_MISMATCH warning code
    has_other_warnings = any(
        code != "BALANCE_MISMATCH"
        for r in runs
        for code in r.warning_codes
    )
    if not stable or has_other_warnings:
        return Color.AMARILLO, stable, drift

    return Color.VERDE, stable, drift


def summarize(runs: list[RunResult], pdf_filename: str, bank_name: str) -> PdfSummary:
    color, stable, drift = classify_pdf(runs)
    distinct: set[str] = set()
    for r in runs:
        distinct.update(r.warning_codes)
    notes_parts: list[str] = []
    if drift:
        notes_parts.append(f"drift:{','.join(drift)}")
    errored = [r for r in runs if r.error]
    if errored:
        notes_parts.append(f"errors:{len(errored)}/{len(runs)}")
    return PdfSummary(
        pdf_filename=pdf_filename,
        bank_name=bank_name,
        color=color,
        stable=stable,
        drift_fields=drift,
        warning_codes_distinct=sorted(distinct),
        runs=runs,
        notes="; ".join(notes_parts),
    )


# ── Runner ────────────────────────────────────────────────────────────────


def _build_bank_account_entry(
    bank_name: str, last4: str, account_type: str, currency: str,
) -> BankAccountEntry:
    """Synthetic entry — same pattern as bootstrap/smoke_cartola_upload.py."""
    safe_bank = bank_name.lower().replace(" ", "-")
    return BankAccountEntry(
        bank_account_id=f"smoke-{safe_bank}-{last4}-{currency.lower()}",
        bank_name=bank_name,
        account_label=f"{bank_name} {account_type} {last4} {currency} (smoke)",
        account_type=account_type,
        entity="EAG",
        currency=currency,
        last4=last4,
        beancount_account=f"Liabilities:EAG:TC:Smoke-{last4}-{currency}",
    )


def run_pdf(
    pdf_path: Path,
    bank_name: str,
    last4: str,
    currency: str,
    account_type: str,
    runs: int,
    gemini: GeminiClient,
    staging_dir: Path,
) -> list[RunResult]:
    """Run a single PDF N times. Errors are captured per-run, never raised."""
    pdf_bytes = pdf_path.read_bytes()
    results: list[RunResult] = []
    for i in range(runs):
        try:
            entry = _build_bank_account_entry(bank_name, last4, account_type, currency)
            batch_id = new_batch_id()
            # Wrap the SDK call with a hard per-call timeout. Without this, a
            # stalled Gemini API call freezes the whole batch (observed 9-5f).
            ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                future = ex.submit(
                    process_upload_sync,
                    batch_id=batch_id,
                    pdf_bytes=pdf_bytes,
                    bank_account_entry=entry,
                    gemini=gemini,
                    staging_dir=staging_dir,
                )
                canonical = future.result(timeout=PER_CALL_TIMEOUT_S)
            finally:
                ex.shutdown(wait=False)
            amounts = [tx.amount for tx in canonical.transactions]
            total = sum(amounts, start=Decimal("0"))
            n_pos = sum(1 for a in amounts if a > 0)
            n_neg = sum(1 for a in amounts if a < 0)
            n_zero = sum(1 for a in amounts if a == 0)
            results.append(RunResult(
                pdf_filename=pdf_path.name,
                run_idx=i + 1,
                bank_name=bank_name,
                n_transactions=len(canonical.transactions),
                opening=canonical.balances.opening,
                closing=canonical.balances.closing,
                sum_amounts=total,
                balance_diff=canonical.balances.closing - canonical.balances.opening - total,
                warning_codes=sorted(w.code for w in canonical.extraction.warnings),
                n_positive=n_pos,
                n_negative=n_neg,
                n_zero=n_zero,
            ))
        except Exception as exc:  # noqa: BLE001 — AC8: capture-all, never abort batch
            err = f"{type(exc).__name__}: {exc}"
            results.append(RunResult(
                pdf_filename=pdf_path.name,
                run_idx=i + 1,
                bank_name=bank_name,
                n_transactions=None,
                opening=None,
                closing=None,
                sum_amounts=None,
                balance_diff=None,
                warning_codes=[],
                n_positive=None,
                n_negative=None,
                n_zero=None,
                error=err,
            ))
    return results


# ── Writers ───────────────────────────────────────────────────────────────


def _fmt_dec(d: Decimal | None) -> str:
    if d is None:
        return ""
    return f"{d:.2f}"


def _fmt_int(n: int | None) -> str:
    return "" if n is None else str(n)


def write_runs_csv(out_dir: Path, summaries: list[PdfSummary]) -> Path:
    path = out_dir / "runs.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "pdf_filename", "run_idx", "bank_name", "color_pdf",
            "n_transactions", "opening", "closing", "sum_amounts", "balance_diff",
            "warning_codes", "error",
        ])
        for s in summaries:
            for r in s.runs:
                w.writerow([
                    r.pdf_filename, r.run_idx, r.bank_name, s.color.value,
                    _fmt_int(r.n_transactions),
                    _fmt_dec(r.opening), _fmt_dec(r.closing),
                    _fmt_dec(r.sum_amounts), _fmt_dec(r.balance_diff),
                    "|".join(r.warning_codes),
                    r.error,
                ])
    return path


def write_summary_csv(out_dir: Path, summaries: list[PdfSummary]) -> Path:
    path = out_dir / "summary.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "pdf_filename", "bank_name", "color",
            "n_runs_stable", "warnings_distinct", "notes",
        ])
        for s in summaries:
            w.writerow([
                s.pdf_filename, s.bank_name, s.color.value,
                "yes" if s.stable else "no",
                "|".join(s.warning_codes_distinct),
                s.notes,
            ])
    return path


def _aggregate_by_bank(summaries: list[PdfSummary]) -> list[tuple[str, int, int, int, int, float]]:
    by_bank: dict[str, dict[str, int]] = {}
    for s in summaries:
        bucket = by_bank.setdefault(s.bank_name, {"total": 0, "verde": 0, "amarillo": 0, "rojo": 0})
        bucket["total"] += 1
        bucket[s.color.value] += 1
    rows: list[tuple[str, int, int, int, int, float]] = []
    for bank, b in sorted(by_bank.items()):
        pct_verde = (b["verde"] / b["total"] * 100) if b["total"] else 0.0
        rows.append((bank, b["total"], b["verde"], b["amarillo"], b["rojo"], pct_verde))
    return rows


def _sign_distribution_by_bank(summaries: list[PdfSummary]) -> list[tuple[str, float, float, float]]:
    by_bank: dict[str, dict[str, int]] = {}
    for s in summaries:
        first = s.runs[0] if s.runs else None
        if first is None or first.n_positive is None:
            continue
        bucket = by_bank.setdefault(s.bank_name, {"pos": 0, "neg": 0, "zero": 0})
        bucket["pos"] += first.n_positive
        bucket["neg"] += first.n_negative or 0
        bucket["zero"] += first.n_zero or 0
    rows: list[tuple[str, float, float, float]] = []
    for bank, b in sorted(by_bank.items()):
        total = b["pos"] + b["neg"] + b["zero"]
        if total == 0:
            rows.append((bank, 0.0, 0.0, 0.0))
            continue
        rows.append((
            bank,
            b["pos"] / total * 100,
            b["neg"] / total * 100,
            b["zero"] / total * 100,
        ))
    return rows


def write_report_md(
    out_dir: Path,
    summaries: list[PdfSummary],
    runs_per_pdf: int,
    elapsed_seconds: float,
    model: str,
    timestamp: str,
) -> Path:
    total = len(summaries)
    n_verde = sum(1 for s in summaries if s.color is Color.VERDE)
    n_amar = sum(1 for s in summaries if s.color is Color.AMARILLO)
    n_rojo = sum(1 for s in summaries if s.color is Color.ROJO)
    pct = (lambda n: (n / total * 100) if total else 0.0)
    pct_verde = pct(n_verde)
    gate = "PASS" if pct_verde >= 90 else "FAIL"

    lines: list[str] = []
    lines.append(f"# Validation run — {timestamp}")
    lines.append(f"- PDFs evaluados: {total}")
    lines.append(f"- Corridas por PDF: {runs_per_pdf}")
    lines.append(f"- Tiempo total: {elapsed_seconds:.1f}s")
    lines.append(f"- Modelo Gemini: {model}")
    lines.append("")
    lines.append("## Resumen")
    lines.append(f"- 🟢 Verde: {n_verde} ({pct_verde:.1f}%)")
    lines.append(f"- 🟡 Amarillo: {n_amar} ({pct(n_amar):.1f}%)")
    lines.append(f"- 🔴 Rojo: {n_rojo} ({pct(n_rojo):.1f}%)")
    lines.append("")
    lines.append(f"**Gate 9.6a (≥90% verde):** {gate}")
    lines.append("")
    lines.append("## Por banco")
    lines.append("| Banco | Total | 🟢 | 🟡 | 🔴 | % verde |")
    lines.append("|---|---|---|---|---|---|")
    for bank, tot, v, a, r, pv in _aggregate_by_bank(summaries):
        lines.append(f"| {bank} | {tot} | {v} | {a} | {r} | {pv:.1f}% |")
    lines.append("")
    lines.append("## Detalle por PDF")
    for s in sorted(summaries, key=lambda x: (x.color.value, x.pdf_filename)):
        lines.append("")
        lines.append(f"### {s.color.emoji} {s.pdf_filename}")
        lines.append(f"- bank: {s.bank_name}")
        lines.append(f"- estable: {'sí' if s.stable else 'no'}"
                     + (f" (drift: {', '.join(s.drift_fields)})" if s.drift_fields else ""))
        if s.warning_codes_distinct:
            counts: dict[str, int] = {}
            for r in s.runs:
                for code in r.warning_codes:
                    counts[code] = counts.get(code, 0) + 1
            wc = ", ".join(f"{c}×{counts[c]}" for c in sorted(counts))
            lines.append(f"- warnings: {wc}")
        else:
            lines.append("- warnings: ninguno")
        lines.append("")
        lines.append("| run | n_tx | opening | closing | sum(amounts) | diff | warnings | error |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for r in s.runs:
            lines.append(
                f"| {r.run_idx} | {_fmt_int(r.n_transactions)} | "
                f"{_fmt_dec(r.opening)} | {_fmt_dec(r.closing)} | "
                f"{_fmt_dec(r.sum_amounts)} | {_fmt_dec(r.balance_diff)} | "
                f"{'|'.join(r.warning_codes)} | {r.error} |"
            )
    lines.append("")
    lines.append("## Sign distribution (agregado, primera corrida de cada PDF)")
    lines.append("| Banco | %positivos | %negativos | %ceros |")
    lines.append("|---|---|---|---|")
    for bank, pos, neg, zero in _sign_distribution_by_bank(summaries):
        lines.append(f"| {bank} | {pos:.1f}% | {neg:.1f}% | {zero:.1f}% |")
    lines.append("")

    path = out_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ── CLI entry point ───────────────────────────────────────────────────────


def _discover_pdfs(directory: Path, explicit: list[Path]) -> list[Path]:
    if explicit:
        return sorted(p for p in explicit)
    if not directory.exists() or not directory.is_dir():
        return []
    return sorted(directory.glob("*.pdf"))


def _default_out_dir() -> Path:
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    return Path("_bmad-output") / "validation-runs" / ts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Batch validation runner for Gemini cartola extraction (Story 9.5c)"
    )
    parser.add_argument("directory", type=Path, nargs="?", default=Path("samples"),
                        help="Directory to scan for *.pdf (default: samples/)")
    parser.add_argument("--pdf", type=Path, action="append", default=[],
                        help="Specific PDF(s) to run; can be repeated. Overrides directory scan.")
    parser.add_argument("--runs", type=int, default=3, help="Runs per PDF (default 3)")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="Output directory (default _bmad-output/validation-runs/{timestamp}/)")
    parser.add_argument("--bank-account-type", default="tarjeta_credito",
                        choices=ACCOUNT_TYPE_CHOICES)
    parser.add_argument("--override", action="append", default=[], type=parse_override,
                        help="<pdf_filename>:<bank_name>:<last4>[:<currency>] (repeatable). "
                             "currency default CLP; CLP|USD|EUR.")
    parser.add_argument("--keep-staging", action="store_true",
                        help="Preserve staging .cartola.json files for manual inspection")
    args = parser.parse_args(argv)

    # Fail-fast on missing API key BEFORE any work.
    if not os.getenv("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY not set (check .env)", file=sys.stderr)
        return 2

    pdfs = _discover_pdfs(args.directory, args.pdf)
    if not pdfs:
        target = args.pdf or args.directory
        print(f"ERROR: no PDFs found at {target}", file=sys.stderr)
        return 2

    overrides: dict[str, tuple[str, str, str]] = {
        filename: (bank, last4, currency)
        for filename, bank, last4, currency in args.override
    }

    out_dir = args.out_dir or _default_out_dir()
    staging_dir = out_dir / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)

    gemini = GeminiClient()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Validation run @ {timestamp}")
    print(f"PDFs: {len(pdfs)} × {args.runs} runs = {len(pdfs) * args.runs} Gemini calls")
    print(f"Model: {gemini.model}")
    print(f"Output: {out_dir}")
    print()

    summaries: list[PdfSummary] = []
    start = time.monotonic()
    for pdf in pdfs:
        bank_name, last4, currency, used_fallback = resolve_pdf_metadata(pdf, overrides)
        if used_fallback:
            print(f"  ⚠ {pdf.name} — no convention match, no override → bank='Desconocido' last4='9999' currency='CLP'")
        print(f"  → {pdf.name} (bank={bank_name}, last4={last4}, currency={currency})")
        try:
            runs = run_pdf(
                pdf_path=pdf,
                bank_name=bank_name,
                last4=last4,
                currency=currency,
                account_type=args.bank_account_type,
                runs=args.runs,
                gemini=gemini,
                staging_dir=staging_dir,
            )
        except Exception as exc:  # noqa: BLE001 — last-resort safety net (run_pdf already catches)
            traceback.print_exc()
            runs = [RunResult(
                pdf_filename=pdf.name, run_idx=1, bank_name=bank_name,
                n_transactions=None, opening=None, closing=None, sum_amounts=None,
                balance_diff=None, warning_codes=[], n_positive=None, n_negative=None,
                n_zero=None, error=f"{type(exc).__name__}: {exc}",
            )]
        summary = summarize(runs, pdf.name, bank_name)
        print(f"    {summary.color.emoji} {summary.color.value}"
              + (f"  drift={','.join(summary.drift_fields)}" if summary.drift_fields else "")
              + (f"  warnings={','.join(summary.warning_codes_distinct)}" if summary.warning_codes_distinct else ""))
        summaries.append(summary)

    elapsed = time.monotonic() - start

    write_runs_csv(out_dir, summaries)
    write_summary_csv(out_dir, summaries)
    write_report_md(
        out_dir=out_dir,
        summaries=summaries,
        runs_per_pdf=args.runs,
        elapsed_seconds=elapsed,
        model=gemini.model,
        timestamp=timestamp,
    )

    if not args.keep_staging:
        shutil.rmtree(staging_dir, ignore_errors=True)

    total = len(summaries)
    n_verde = sum(1 for s in summaries if s.color is Color.VERDE)
    pct_verde = (n_verde / total * 100) if total else 0.0
    gate = "PASS" if pct_verde >= 90 else "FAIL"
    print()
    print(f"Done — {n_verde}/{total} verde ({pct_verde:.1f}%) | gate ≥90%: {gate}")
    print(f"Report: {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
