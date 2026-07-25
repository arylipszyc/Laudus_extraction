"""
Spike Odoo — exporta un mes del ledger Beancount a CSVs importables por Odoo.

Genera, por entidad legal (EAG = RUT1, RUT2 = FFCC/JAB):
  - accounts_<COMPANY>.csv   -> import de account.account (plan de cuentas)
  - moves_<COMPANY>_<YYYY-MM>.csv -> import de account.move + line_ids (asientos)

El CSV de asientos usa el formato o2m de Odoo: la primera fila de cada asiento
lleva cabecera (id/date/ref/journal) + su primera pata; las patas siguientes van
con id vacío y solo columnas line_ids/*.

Uso:  ../venv/Scripts/python.exe export_laudus_to_odoo.py 2026 5
"""
import csv
import os
import sys
from collections import defaultdict

from beancount import loader
from beancount.core import data

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
LEDGER = os.path.join(REPO, "ledger", "main.beancount")
OUTDIR = os.path.join(HERE, "csv")

# Sub-entidades que pertenecen a la 2da entidad legal (RUT2 = Fondo Comun).
# El resto (EAG + hijas) es RUT1 = company "EAG".
RUT2_SEGMENTS = {"FFCC", "JAB"}


def company_of_account(account: str) -> str:
    seg = account.split(":")[1]
    return "RUT2" if seg in RUT2_SEGMENTS else "EAG"


def account_type(account: str, meta: dict) -> str:
    """Mapeo grueso Beancount root -> Odoo account_type (afinar despues)."""
    root = account.split(":")[0]
    if root == "Assets":
        return "asset_cash" if meta.get("bank_account_id") else "asset_current"
    if root == "Liabilities":
        return "liability_current"
    if root == "Equity":
        return "equity"
    if root == "Income":
        return "income"
    if root == "Expenses":
        return "expense"
    return "asset_current"


def group_path(meta: dict) -> str:
    parts = [meta.get(k, "") for k in ("laudus_categoria1", "laudus_categoria2", "laudus_categoria3")]
    return " / ".join(p for p in parts if p)


def main(year: int, month: int):
    os.makedirs(OUTDIR, exist_ok=True)
    print(f"Cargando {LEDGER} ...")
    entries, errors, _ = loader.load_file(LEDGER)
    print(f"  entries={len(entries)}  errores_carga={len(errors)}")

    # --- Plan de cuentas: name -> (code, company, type, currency, group) ---
    acc_by_company = defaultdict(list)   # company -> list of row dicts
    code_of = {}                          # account name -> code (para las patas)
    for e in entries:
        if not isinstance(e, data.Open):
            continue
        code = e.meta.get("code")
        if not code:
            continue  # cuentas tecnicas sin code Laudus se saltan
        company = company_of_account(e.account)
        currency = e.currencies[0] if e.currencies else "CLP"
        ext_id = f"acc_{company}_{code}"
        code_of[e.account] = (code, company)
        acc_by_company[company].append({
            "id": ext_id,
            "code": code,
            "name": e.meta.get("laudus_account_name") or e.account.split(":")[-1],
            "account_type": account_type(e.account, e.meta),
            "currency": currency,
            "laudus_group": group_path(e.meta),
        })

    for company, rows in acc_by_company.items():
        path = os.path.join(OUTDIR, f"accounts_{company}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "code", "name", "account_type", "currency", "laudus_group"])
            w.writeheader()
            w.writerows(rows)
        print(f"  {os.path.basename(path)}: {len(rows)} cuentas")

    # --- Asientos del mes, por company ---
    moves_by_company = defaultdict(list)  # company -> list of (txn)
    for e in entries:
        if not isinstance(e, data.Transaction):
            continue
        if e.date.year != year or e.date.month != month:
            continue
        company = e.meta.get("entity")
        if company not in ("EAG", "RUT2"):
            # fallback por si algun asiento no trae entity
            company = company_of_account(e.postings[0].account)
        moves_by_company[company].append(e)

    ym = f"{year:04d}-{month:02d}"
    for company, txns in moves_by_company.items():
        path = os.path.join(OUTDIR, f"moves_{company}_{ym}.csv")
        n_lines = 0
        dbt = cdt = 0
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "id", "date", "ref", "journal_id",
                "line_ids/account_id/id", "line_ids/name",
                "line_ids/debit", "line_ids/credit",
            ])
            for t in txns:
                move_id = f"mv_{company}_{t.meta.get('id')}"
                ref = t.narration or t.meta.get("je_num", "")
                first = True
                for p in t.postings:
                    amt = p.units.number
                    debit = amt if amt > 0 else 0
                    credit = -amt if amt < 0 else 0
                    dbt += float(debit)
                    cdt += float(credit)
                    code_company = code_of.get(p.account)
                    acc_ext = f"acc_{code_company[1]}_{code_company[0]}" if code_company else ""
                    line_name = (p.meta or {}).get("desc") or ref
                    if first:
                        w.writerow([move_id, t.date.isoformat(), ref, "Diario Laudus",
                                    acc_ext, line_name, f"{debit:.2f}", f"{credit:.2f}"])
                        first = False
                    else:
                        w.writerow(["", "", "", "",
                                    acc_ext, line_name, f"{debit:.2f}", f"{credit:.2f}"])
                    n_lines += 1
        print(f"  {os.path.basename(path)}: {len(txns)} asientos, {n_lines} patas, "
              f"debe={dbt:,.0f} haber={cdt:,.0f} desc={dbt - cdt:,.0f}")


if __name__ == "__main__":
    y = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    m = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    main(y, m)
