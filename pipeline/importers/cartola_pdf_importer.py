"""CartolaPdfImporter — JSON canónico (Story 9.5) → directivas Beancount (Story 9.6a).

Parser básico del path "match perfecto": cada transaction → `data.Transaction`,
+ una `data.Balance` al cierre del período (bean-check valida el cuadre, FR22-25).
SIN reconciliación cross-source (eso es 9.6b).

**Convención de signo (verificada contra cartolas reales 2026-06-10):**
La cartola presenta montos/saldos en convención "natural de extracto" — para una
TC, `opening`/`closing` y cargos son POSITIVOS (deuda como número positivo),
`opening + Σ amounts = closing`. Beancount usa liabilities crédito-normal
(deuda negativa, ver opening balances). Por eso, para cuentas Liabilities se
NIEGA el signo (`target = -amount`, `balance = -closing`); para Assets se usa
tal cual. Ambos postings suman 0.

> NOTA: AC4 del storyfile describe los postings como `Liabilities +X` y
> `Expenses +X` "que suman 0" — eso es imposible en beancount (sumaría 2X). La
> implementación sigue el gate real (AC5 = bean-check pasa), verificado con la
> aritmética de un sample real. Ver Completion Notes.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import beangulp
from beancount.core import data
from beancount.core.amount import Amount
from beancount.parser import printer

from backend.app.integrations.cartola_schema import CartolaCanonicalV1
from bootstrap.account_mapping import slugify
from pipeline.importers.bank_account_resolver import BankAccountResolver
from pipeline.importers.category_predictor import CategoryPredictor, NoopCategoryPredictor

logger = logging.getLogger(__name__)

DISCREPANCIAS_ACCOUNT = "Equity:Reconciliation:Discrepancias"
_LIABILITY_ROOT = "Liabilities"


def _build_postings(
    account_target: str,
    category_account: str,
    amount: Decimal,
    currency: str,
    is_liability: bool,
) -> list[data.Posting]:
    """Two balanced postings (AC4, corrected for beancount sign convention).

    is_liability → negate (statement-natural debt-positive → beancount debt-negative).
    """
    sign = Decimal(-1) if is_liability else Decimal(1)
    target_num = sign * amount
    return [
        data.Posting(account_target, Amount(target_num, currency), None, None, None, None),
        data.Posting(category_account, Amount(-target_num, currency), None, None, None, None),
    ]


def build_usd_postings(
    account_target: str,
    category_account: str,
    usd_amount: Decimal,
    fx_implied: Decimal,
    is_liability: bool,
) -> list[data.Posting]:
    """Postings de una línea USD con price per-unit CLP (Story 9.6b AC2/AC8).

    El posting del banco/TC lleva las unidades USD con `@ fx_implied CLP` (per-unit; equivale
    al `@@ total` del storyfile y es lo que beancount serializa). El plugin `implicit_prices`
    deriva la price directive. La contrapartida en CLP cierra el balance por construcción.
    """
    sign = Decimal(-1) if is_liability else Decimal(1)
    usd_units = sign * usd_amount
    clp_weight = (usd_units * fx_implied).quantize(Decimal("0.01"))
    price = Amount(fx_implied, "CLP")
    return [
        data.Posting(account_target, Amount(usd_units, "USD"), None, price, None, None),
        data.Posting(category_account, Amount(-clp_weight, "CLP"), None, None, None, None),
    ]


def fx_metadata(fx_result, bank_slug: str, year_month: str) -> dict:
    """Metadata FX para la Transaction (todos strings, convención Beancount) — AC8."""
    meta = {"fx_source": f"derived-cartola-{bank_slug}-{year_month}"}
    if fx_result.implied is not None:
        meta["fx_implied"] = str(fx_result.implied)
    if fx_result.bcch is not None:
        meta["fx_bcch"] = str(fx_result.bcch)
    if fx_result.deviation_pct is not None:
        meta["fx_deviation_pct"] = str(fx_result.deviation_pct)
    return meta


class CartolaPdfImporter(beangulp.Importer):
    """beangulp.Importer: `{batch_id}.cartola.json` → directivas Beancount."""

    def __init__(
        self,
        bank_account_resolver: BankAccountResolver,
        category_predictor: CategoryPredictor | None = None,
    ) -> None:
        self.resolver = bank_account_resolver
        self.category_predictor = category_predictor or NoopCategoryPredictor()

    # ── beangulp interface ──────────────────────────────────────────────────

    def identify(self, filepath: str) -> bool:
        if not str(filepath).endswith(".cartola.json"):
            return False
        try:
            payload = json.loads(Path(filepath).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        return str(payload.get("schema_version", "")).startswith("1.")

    def account(self, filepath: str) -> str:
        payload = json.loads(Path(filepath).read_text(encoding="utf-8"))
        return self.resolver.resolve(payload["source"]["bank_account_id"])

    def extract(self, filepath: str, existing=None) -> list:
        model = CartolaCanonicalV1.model_validate_json(Path(filepath).read_text(encoding="utf-8"))
        account_target = self.resolver.resolve(model.source.bank_account_id)
        is_liability = account_target.startswith(_LIABILITY_ROOT)

        entries: list = []
        for tx in model.transactions:
            category_account, match_source, flag = self.category_predictor.predict(
                tx.description, tx.amount, model.source.bank_account_id
            )
            # category_status: confirmed solo cuando el motor está confiado (flag "*").
            category_status = "pending" if match_source == "pending" else (
                "confirmed" if flag == "*" else "suggested")
            meta = data.new_metadata(filepath, tx.line_no)
            meta.update({
                "source": "cartola-pdf",
                "bank_account_id": model.source.bank_account_id,
                "batch_id": Path(filepath).name.removesuffix(".cartola.json"),
                "match_source": match_source,
                "category_status": category_status,
                "extraction_model": model.extraction.model,
                "line": str(tx.line_no),
            })
            postings = _build_postings(account_target, category_account, tx.amount, tx.currency, is_liability)
            entries.append(data.Transaction(
                meta=meta,
                date=tx.date,
                flag=flag,
                payee=None,
                narration=tx.description or f"line {tx.line_no}",
                tags=frozenset(),
                links=frozenset(),
                postings=postings,
            ))

        # Closing balance assertion at period.end + 1 day (start-of-day semantics).
        sign = Decimal(-1) if is_liability else Decimal(1)
        bal_meta = data.new_metadata(filepath, 0)
        entries.append(data.Balance(
            meta=bal_meta,
            date=model.period.end + timedelta(days=1),
            account=account_target,
            amount=Amount(sign * model.balances.closing, model.currency),
            tolerance=None,
            diff_amount=None,
        ))
        return entries


# ── Override: Balance → pad + balance (AC6) ─────────────────────────────────


def convert_balance_to_pad(
    entries: list,
    override_justification: str,
    override_user: str,
    override_at: str,
    discrepancias_account: str = DISCREPANCIAS_ACCOUNT,
) -> list:
    """Replace the closing `Balance` with `pad ... Discrepancias` + `balance` (FR25)."""
    out: list = []
    for entry in entries:
        if isinstance(entry, data.Balance):
            pad_meta = data.new_metadata("<override>", 0)
            pad_meta.update({
                "override_justification": override_justification,
                "override_user": override_user,
                "override_at": override_at,
            })
            # El pad debe datear ANTES del Balance: los balance checks de beancount son
            # start-of-day, así que un pad con la misma fecha no alcanza a aplicarse
            # ("Unused Pad entry"). Un día antes garantiza que el padding entre antes del check.
            out.append(data.Pad(pad_meta, entry.date - timedelta(days=1), entry.account, discrepancias_account))
        out.append(entry)
    return out


# ── Promotion (AC7/AC8) ─────────────────────────────────────────────────────


def _slug(model: CartolaCanonicalV1, last4: str | None) -> str:
    bank = slugify(model.source.bank_name) or "Banco"
    tail = last4 or "xxxx"
    return f"{bank}-{tail}-{model.period.end.strftime('%Y-%m')}"


def render_entries(entries: list) -> str:
    """Serialize entries to deterministic Beancount text (idempotent, AC7)."""
    return "".join(printer.format_entry(e) for e in entries)


def promote(
    batch_id: str,
    importer: CartolaPdfImporter,
    ledger_root,
    override: dict | None = None,
) -> dict:
    """Staging JSON → final `imports/cartolas/{slug}.beancount` + bean-check + git.

    git push is guarded by `IMPORTER_GIT_ENABLED` (same as Story 9.4). On bean-check
    failure, the output file is removed and the staging file is left intact.

    `override` (Story 9.9 AC4): `{justification, user, at}` → la `Balance` de cierre se
    convierte en `pad`+`balance` (la pad absorbe la discrepancia → bean-check pasa) y el
    commit message marca `OVERRIDE pad+balance`. La metadata del override queda en la directiva.
    """
    from pipeline.importers.laudus_run import acquire_lock, bean_check, git_commit_push

    root = Path(ledger_root)
    staging = root / "imports" / "cartolas" / "_staging" / f"{batch_id}.cartola.json"
    out_dir = root / "imports" / "cartolas"
    main_path = root / "main.beancount"
    lock_path = root / ".import.lock"

    model = CartolaCanonicalV1.model_validate_json(staging.read_text(encoding="utf-8"))
    resolved = importer.resolver.get(model.source.bank_account_id)
    out_file = out_dir / f"{_slug(model, resolved.last4)}.beancount"

    result = {"batch_id": batch_id, "file": str(out_file), "tx": len(model.transactions),
              "success": False, "error_msg": None, "git_commit_sha": None, "override": bool(override)}

    with acquire_lock(lock_path):
        entries = importer.extract(str(staging))
        if override:
            entries = convert_balance_to_pad(
                entries, override["justification"], override["user"], override["at"])
        out_file.write_text(render_entries(entries), encoding="utf-8")

        ok, detail = bean_check(main_path)
        if not ok:
            out_file.unlink(missing_ok=True)
            result["error_msg"] = f"bean-check failed: {detail}"
            logger.error(result["error_msg"])
            return result

        staging.unlink(missing_ok=True)
        suffix = ", OVERRIDE pad+balance" if override else ""
        message = (f"[importer-cartola] {slugify(model.source.bank_name)} "
                   f"{model.period.end.strftime('%Y-%m')}: +{len(model.transactions)} tx{suffix}")
        result["git_commit_sha"] = git_commit_push(
            root, [f"ledger/imports/cartolas/{out_file.name}"], message,
        )
        result["success"] = True
        logger.info(message)
        return result
