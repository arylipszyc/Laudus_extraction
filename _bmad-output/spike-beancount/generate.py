"""
Spike — Beancount viability check.
Pulls ~10 journal entries from `ledger_eag` Google Sheet, maps Categoria1 to
Beancount root accounts (Assets / Liabilities / Equity / Income / Expenses),
emits a self-contained `eag.beancount` file ready for `bean-check` and `fava`.

NOT production code. Spike artifact for the c3 (Fava + extensions) decision.
"""

import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.config.gspread_config import get_spreadsheet  # noqa: E402

OUT = Path(__file__).parent / "eag.beancount"

# Category1 → Beancount root + entity sub-account
ROOT_MAP = {
    "ACTIVO EAG": ("Assets", "EAG"),
    "PASIVO": ("Liabilities", "EAG"),
    "GASTOS - EGRESOS": ("Expenses", "EAG"),
    "INGRESOS": ("Income", "EAG"),
    "DISPONIBLE JOCELYN AVAYU DEUTSCH": ("Assets", "Jocelyn"),
    "EGRESOS JOCELYN AVAYU DEUTSCH": ("Expenses", "Jocelyn"),
    "INGRESOS JOCELYN AVAYU DEUTSCH": ("Income", "Jocelyn"),
    "DISPONIBLE JAEL AVAYU DEUTSCH": ("Assets", "Jael"),
    "EGRESOS JAEL AVAYU DEUTSCH": ("Expenses", "Jael"),
    "INGRESOS JAEL AVAYU DEUTSCH": ("Income", "Jael"),
    "DISPONIBLE JOHANNA AVAYU DEUTSCH": ("Assets", "Johanna"),
    "EGRESOS JOHANNA AVAYU DEUTSCH": ("Expenses", "Johanna"),
    "INGRESOS JOHANNA AVAYU DEUTSCH": ("Income", "Johanna"),
    "DISPONIBLE JEANNETTE AVAYU DEUTSCH": ("Assets", "Jeannette"),
    "EGRESOS JEANNETTE AVAYU DEUTSCH": ("Expenses", "Jeannette"),
    "INGRESOS JEANNETTE AVAYU DEUTSCH": ("Income", "Jeannette"),
}


def slug(s: str) -> str:
    """Beancount account components: must start uppercase, no spaces, ASCII."""
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    parts = [p.capitalize() for p in re.split(r"[\s\-_]+", s) if p]
    out = "".join(parts)
    out = re.sub(r"[^A-Za-z0-9]", "", out)
    if not out or not out[0].isupper():
        out = "X" + out
    return out


def to_account(cat1: str, account_number: str, account_name: str) -> str | None:
    if cat1 not in ROOT_MAP:
        return None
    root, entity = ROOT_MAP[cat1]
    return f"{root}:{entity}:{slug(account_name)}-{account_number}"


def main():
    sh = get_spreadsheet()
    rows = sh.worksheet("ledger_eag").get_all_records()

    # Group by JE
    by_je = defaultdict(list)
    for r in rows:
        by_je[r["journalentryid"]].append(r)

    # Pick clean balanced 2-posting JEs across years and entities
    picked = []
    seen_years = set()
    seen_entities = set()
    target = 12

    for je_id, postings in by_je.items():
        if len(postings) != 2:
            continue
        d = sum(float(p["debit"] or 0) for p in postings)
        c = sum(float(p["credit"] or 0) for p in postings)
        if abs(d - c) > 0.01 or d == 0:
            continue
        # Map all postings — skip JE if any cat1 unknown
        mapped = []
        ok = True
        for p in postings:
            acc = to_account(p["Categoria1"], p["accountnumber"], p["accountName"])
            if not acc:
                ok = False
                break
            mapped.append((p, acc))
        if not ok:
            continue
        try:
            year = datetime.fromisoformat(postings[0]["date"].replace(" 0:00:00", "")).year
        except Exception:
            continue
        ent_key = tuple(sorted(set(ROOT_MAP[p["Categoria1"]][1] for p in postings)))
        # Bias: get spread across years and entities, but allow duplicates after coverage
        if len(picked) < target:
            if year not in seen_years or ent_key not in seen_entities or len(picked) >= 6:
                picked.append((je_id, postings, mapped))
                seen_years.add(year)
                seen_entities.add(ent_key)
        else:
            break

    print(f"Picked {len(picked)} JEs")

    # Collect all unique accounts used
    accounts = {}
    for _, _, mapped in picked:
        for p, acc in mapped:
            if acc not in accounts:
                accounts[acc] = (p["Categoria1"], p["accountName"], p["accountnumber"])

    # Earliest open date = earliest tx date - 1 day
    tx_dates = [datetime.fromisoformat(p["date"].replace(" 0:00:00", "")).date()
                for _, postings, _ in picked for p in postings]
    open_date = min(tx_dates)

    # Write .beancount
    lines = []
    lines.append('option "title" "EAG — Family Office (spike Beancount)"')
    lines.append('option "operating_currency" "CLP"')
    lines.append('')
    lines.append(f';; --- spike: {len(picked)} JEs from ledger_eag, generated {datetime.now().isoformat(timespec="seconds")}')
    lines.append('')
    lines.append(f';; Account opens')
    for acc, (cat1, name, num) in sorted(accounts.items()):
        lines.append(f'{open_date} open {acc} CLP')
        lines.append(f'  laudus_account_number: "{num}"')
        lines.append(f'  laudus_account_name: "{name}"')
        lines.append(f'  laudus_categoria1: "{cat1}"')
    lines.append('')
    lines.append(';; Transactions')

    for je_id, postings, mapped in sorted(picked, key=lambda x: x[1][0]["date"]):
        date = datetime.fromisoformat(postings[0]["date"].replace(" 0:00:00", "")).date()
        narration = postings[0]["description"] or "(sin descripción)"
        narration = narration.replace('"', "'")
        lines.append(f'{date} * "{narration}"')
        lines.append(f'  laudus_je_id: "{je_id}"')
        for p, acc in mapped:
            d = float(p["debit"] or 0)
            c = float(p["credit"] or 0)
            amount = d if d > 0 else -c
            lines.append(f'  {acc}  {amount:.2f} CLP')
        lines.append('')

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"Accounts: {len(accounts)} | Transactions: {len(picked)}")


if __name__ == "__main__":
    main()
