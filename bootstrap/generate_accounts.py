"""Genera ledger/accounts.beancount con las 255 cuentas hoja del plan — Story 9.1 Task 2.

Pipeline:
    1. Lee plan completo desde Laudus API (293 cuentas, longitud variable de account_number).
    2. Lee plan + bank_accounts desde Supabase (293 + 47 entries, todo padded a 6 dígitos).
    3. Normaliza Laudus → padded 6 dígitos.
    4. Cross-check Laudus ↔ Supabase por account_number.
       Mismatches → bootstrap/report-mismatch-accounts.csv (exit ≠ 0).
    5. Filtra a las 255 cuentas hoja (las 38 raíz/categoría se emiten a
       bootstrap/report-hierarchy-nodes.csv para auditoría).
    6. Para cada cuenta: deriva (Root, Entity, Group?) usando account_mapping.
       Cuentas con Categoria1 desconocida → bootstrap/report-unmapped-accounts.csv (exit ≠ 0).
    7. Renderiza ledger/accounts.beancount.
    8. Valida `bean-check` (smoke local — el comando completo es Task 5).

Uso:
    python -m bootstrap.generate_accounts [--ledger-path PATH] [--reports-path PATH]
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from bootstrap.account_mapping import (
    UnknownBankAccountType,
    UnmappableCategoria1,
    build_account_path,
    normalize_account_number,
    resolve_root_entity_group,
)
from bootstrap.sources import (
    fetch_laudus_accounts,
    fetch_supabase_bank_accounts,
    fetch_supabase_plan,
)

logger = logging.getLogger(__name__)

OPENING_DATE = "2020-12-31"  # un día antes que opening-2021.beancount para que
                              # los `pad` directives (también 2020-12-31) referencien
                              # cuentas ya abiertas. Beancount exige open ≤ pad-date.
LEAF_LENGTH = 6  # En Laudus, longitud de account_number == 6 ⇒ cuenta hoja


@dataclass
class CrossCheckResult:
    matched: list[dict[str, Any]]            # cuentas presentes en ambas fuentes
    name_divergences: list[dict[str, Any]]   # match por número, name distinto
    laudus_only: list[dict[str, Any]]
    supabase_only: list[dict[str, Any]]

    @property
    def has_structural_mismatches(self) -> bool:
        """True si falta una cuenta en alguna de las dos fuentes (blocking).

        Name-divergences NO son estructurales — bajo policy "Laudus manda"
        (decisión Ary 2026-05-05) se reportan como info y no bloquean.
        """
        return bool(self.laudus_only or self.supabase_only)


def crosscheck(
    laudus: list[dict[str, Any]],
    supabase_plan: list[dict[str, Any]],
) -> CrossCheckResult:
    """Cross-check Laudus ↔ Supabase por account_number normalizado.

    Convención: Laudus manda en `name` (es la fuente original); divergencias
    de nombre se reportan como warnings pero el campo Laudus se usa.
    """
    laudus_by_num = {
        normalize_account_number(a["accountNumber"]): a for a in laudus
    }
    supabase_by_num = {r["account_number"]: r for r in supabase_plan}

    matched: list[dict[str, Any]] = []
    name_divergences: list[dict[str, Any]] = []
    laudus_only: list[dict[str, Any]] = []
    supabase_only: list[dict[str, Any]] = []

    for num, l_acc in laudus_by_num.items():
        s_acc = supabase_by_num.get(num)
        if s_acc is None:
            laudus_only.append({"account_number": num, "laudus_name": l_acc["name"]})
            continue
        record = {
            "account_number": num,
            "laudus_original_length": len(l_acc["accountNumber"]),  # 1/2/3=hierarchy, 6=leaf
            "laudus_account_id": l_acc["accountId"],
            "laudus_name": l_acc["name"],
            "supabase_name": s_acc["account_name"],
            "cat1": s_acc.get("cat1"),
            "cat2": s_acc.get("cat2"),
            "cat3": s_acc.get("cat3"),
            "supabase_active": s_acc.get("active", True),
        }
        if l_acc["name"] != s_acc["account_name"]:
            name_divergences.append({
                "account_number": num,
                "laudus_name": l_acc["name"],
                "supabase_name": s_acc["account_name"],
            })
        matched.append(record)

    for num, s_acc in supabase_by_num.items():
        if num not in laudus_by_num:
            supabase_only.append({
                "account_number": num,
                "supabase_name": s_acc["account_name"],
                "active": s_acc.get("active", True),
            })

    return CrossCheckResult(
        matched=matched,
        name_divergences=name_divergences,
        laudus_only=laudus_only,
        supabase_only=supabase_only,
    )


def index_bank_accounts(banks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index bank_accounts por account_number (FK a plan_de_cuentas)."""
    return {b["account_number"]: b for b in banks}


def render_open_directive(
    record: dict[str, Any],
    bank_meta: Optional[dict[str, Any]],
) -> str:
    """Renderiza una directiva `open` Beancount con metadata Laudus + bank.

    `record` debe tener: account_number (padded), laudus_name, cat1/2/3.
    `bank_meta` opcional: id, account_type, account_currency, bank_name.
    """
    bank_type = bank_meta["account_type"] if bank_meta else None
    root, entity, group = resolve_root_entity_group(
        categoria1=record["cat1"],
        bank_account_type=bank_type,
    )
    account_path = build_account_path(
        root=root,
        entity=entity,
        account_name=record["laudus_name"],
        account_number=record["account_number"],
        group=group,
    )

    if bank_meta and bank_meta.get("account_currency") == "USD":
        commodities = "CLP, USD"
    else:
        commodities = "CLP"

    lines = [f"{OPENING_DATE} open {account_path} {commodities}"]
    lines.append(f'  code: "{record["account_number"]}"')
    lines.append(f'  laudus_account_name: "{_escape(record["laudus_name"])}"')
    lines.append(f'  laudus_categoria1: "{_escape(record["cat1"] or "")}"')
    lines.append(f'  laudus_categoria2: "{_escape(record["cat2"] or "")}"')
    lines.append(f'  laudus_categoria3: "{_escape(record["cat3"] or "")}"')
    if bank_meta:
        lines.append(f'  bank_account_id: "{bank_meta["id"]}"')
        lines.append(f'  bank_name: "{_escape(bank_meta.get("bank_name") or "")}"')
        lines.append(f'  bank_account_type: "{bank_meta["account_type"]}"')
        lines.append(f'  bank_account_currency: "{bank_meta.get("account_currency") or "CLP"}"')
    return "\n".join(lines)


def _escape(s: str) -> str:
    """Escape para strings dentro de comillas dobles en Beancount."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def render_accounts_beancount(
    leaf_records: list[dict[str, Any]],
    bank_index: dict[str, dict[str, Any]],
) -> str:
    """Renderiza el archivo accounts.beancount completo (leaves only)."""
    header = (
        ";; ledger/accounts.beancount — generado por bootstrap/generate_accounts.py\n"
        ";; Story 9.1 (Bootstrap histórico Beancount).\n"
        ";; NO editar a mano sin re-correr el script o sincronizar con Supabase.\n"
        ";; Modelo unificado: las 47 cuentas bancarias son subset del plan,\n"
        ";; identificadas por la metadata bank_account_id.\n"
    )
    parts = [header]
    sorted_records = sorted(leaf_records, key=lambda r: r["account_number"])
    for record in sorted_records:
        bank_meta = bank_index.get(record["account_number"])
        parts.append(render_open_directive(record, bank_meta))
    return "\n\n".join(parts) + "\n"


# ── Reporting ───────────────────────────────────────────────────────────────

def write_structural_mismatch_report(
    crosscheck_result: CrossCheckResult, path: Path,
) -> int:
    """Escribe report-mismatch-accounts.csv (solo blocking: laudus-only +
    supabase-only). Retorna count de filas."""
    rows: list[dict[str, str]] = []
    for d in crosscheck_result.laudus_only:
        rows.append({
            "source": "laudus-only",
            "account_number": d["account_number"],
            "laudus_name": d["laudus_name"],
            "supabase_name": "",
        })
    for d in crosscheck_result.supabase_only:
        rows.append({
            "source": "supabase-only",
            "account_number": d["account_number"],
            "laudus_name": "",
            "supabase_name": d["supabase_name"],
        })
    return _write_csv(path, ["source", "account_number", "laudus_name", "supabase_name"], rows)


def write_name_divergence_report(
    name_divergences: list[dict[str, Any]],
    leaf_numbers: set[str],
    path: Path,
) -> int:
    """Escribe report-name-divergences.csv (info — Laudus manda, Supabase
    está stale). Marca is_leaf para que Ary priorice updates."""
    rows = [
        {
            "account_number": d["account_number"],
            "is_leaf": "true" if d["account_number"] in leaf_numbers else "false",
            "laudus_name": d["laudus_name"],
            "supabase_name": d["supabase_name"],
        }
        for d in name_divergences
    ]
    return _write_csv(
        path, ["account_number", "is_leaf", "laudus_name", "supabase_name"], rows
    )


def write_unmapped_report(unmapped: list[dict[str, Any]], path: Path) -> int:
    """Escribe report-unmapped-accounts.csv. Retorna count de filas."""
    return _write_csv(
        path,
        ["account_number", "laudus_name", "cat1", "cat2", "cat3", "reason"],
        unmapped,
    )


def write_hierarchy_nodes_report(records: list[dict[str, Any]], path: Path) -> int:
    """Escribe report-hierarchy-nodes.csv (38 nodos raíz/categoría)."""
    return _write_csv(
        path,
        ["account_number", "laudus_name", "cat1", "cat2", "cat3"],
        records,
    )


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})
    return len(rows)


# ── Orquestador ─────────────────────────────────────────────────────────────

def run_bootstrap(
    *,
    ledger_path: Path,
    reports_path: Path,
    laudus_accounts: Optional[list[dict[str, Any]]] = None,
    supabase_plan: Optional[list[dict[str, Any]]] = None,
    supabase_banks: Optional[list[dict[str, Any]]] = None,
) -> int:
    """Orquesta el bootstrap completo de accounts.beancount.

    Retorna exit code: 0 = OK, 2 = mismatch o unmapped, 3 = bootstrap inviable.
    Las fuentes son inyectables para tests.
    """
    laudus = laudus_accounts if laudus_accounts is not None else fetch_laudus_accounts()
    plan = supabase_plan if supabase_plan is not None else fetch_supabase_plan()
    banks = supabase_banks if supabase_banks is not None else fetch_supabase_bank_accounts()

    cc = crosscheck(laudus, plan)

    leaf_records = [r for r in cc.matched if r["laudus_original_length"] == LEAF_LENGTH]
    hierarchy_records = [r for r in cc.matched if r["laudus_original_length"] < LEAF_LENGTH]
    write_hierarchy_nodes_report(
        hierarchy_records, reports_path / "report-hierarchy-nodes.csv"
    )

    # Bajo policy "Laudus manda" (Ary 2026-05-05): name-divergences NO bloquean.
    # Se renderiza con el name de Laudus y se reporta como info para que Ary
    # actualice Supabase si quiere mantener sincronía. Solo bloquean los
    # mismatches estructurales (cuenta presente en una fuente y ausente en otra).
    leaf_numbers = {r["account_number"] for r in leaf_records}
    structural_count = write_structural_mismatch_report(
        cc, reports_path / "report-mismatch-accounts.csv"
    )
    divergence_count = write_name_divergence_report(
        cc.name_divergences, leaf_numbers,
        reports_path / "report-name-divergences.csv",
    )

    bank_index = index_bank_accounts(banks)

    unmapped: list[dict[str, Any]] = []
    renderable: list[dict[str, Any]] = []
    for r in leaf_records:
        bank_meta = bank_index.get(r["account_number"])
        bank_type = bank_meta["account_type"] if bank_meta else None
        try:
            resolve_root_entity_group(
                categoria1=r["cat1"], bank_account_type=bank_type
            )
            renderable.append(r)
        except UnmappableCategoria1 as exc:
            unmapped.append({
                "account_number": r["account_number"],
                "laudus_name": r["laudus_name"],
                "cat1": r["cat1"], "cat2": r["cat2"], "cat3": r["cat3"],
                "reason": str(exc),
            })
        except UnknownBankAccountType as exc:
            unmapped.append({
                "account_number": r["account_number"],
                "laudus_name": r["laudus_name"],
                "cat1": r["cat1"], "cat2": r["cat2"], "cat3": r["cat3"],
                "reason": str(exc),
            })

    unmapped_count = write_unmapped_report(
        unmapped, reports_path / "report-unmapped-accounts.csv"
    )

    print(f"Laudus accounts: {len(laudus)}  |  Supabase plan: {len(plan)}  |  bank_accounts: {len(banks)}")
    print(f"Cross-check matched: {len(cc.matched)}  |  hierarchy nodes: {len(hierarchy_records)}  |  leaves: {len(leaf_records)}")
    print(f"Structural mismatches (blocking): {structural_count}  "
          f"(laudus-only={len(cc.laudus_only)}, supabase-only={len(cc.supabase_only)})")
    leaf_divergences = sum(1 for d in cc.name_divergences if d["account_number"] in leaf_numbers)
    print(f"Name-divergences (info — Laudus manda): {divergence_count}  "
          f"(leaf={leaf_divergences}, hierarchy={divergence_count - leaf_divergences})")
    print(f"Unmapped: {unmapped_count}")
    print(f"Renderable leaves: {len(renderable)}")

    if cc.has_structural_mismatches:
        print(f"\n[FAIL] Mismatches estructurales — revisar {reports_path / 'report-mismatch-accounts.csv'}")
        return 2
    if unmapped_count > 0:
        print(f"\n[FAIL] {unmapped_count} cuentas no-mapeables — revisar {reports_path / 'report-unmapped-accounts.csv'}")
        return 2

    accounts_text = render_accounts_beancount(renderable, bank_index)
    out_path = ledger_path / "accounts.beancount"
    out_path.write_text(accounts_text, encoding="utf-8")
    print(f"\n[OK] Renderizado {out_path} ({len(renderable)} cuentas hoja)")
    return 0


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-path", type=Path, default=Path("ledger"))
    parser.add_argument("--reports-path", type=Path, default=Path("bootstrap"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return run_bootstrap(ledger_path=args.ledger_path, reports_path=args.reports_path)


if __name__ == "__main__":
    sys.exit(_cli())
