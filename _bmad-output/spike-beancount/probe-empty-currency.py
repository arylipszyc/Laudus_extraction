"""
Probe: investigate the 172 lines with currencyCode='' and parityToMainCurrency=0.
"""
import sys
sys.path.insert(0, r"c:\dev\bmad-workspace\LAUDUS_Backup")

from pipeline.services.ledger_service import fetch_ledger
from pipeline.config.laudus_config import LEDGER_URL
import datetime

date_to = datetime.date.today()
date_from = datetime.date(2024, 1, 1)

records = fetch_ledger(LEDGER_URL, params={
    "dateFrom": str(date_from), "dateTo": str(date_to), "accountNumberFrom": "1"
})

empty = [r for r in records if (r.get("currencyCode") or "") == ""]
print(f"Total empty-currency lines: {len(empty)}")

# Show field shape of one
print("\n--- Field shape of one empty line ---")
print(empty[0])

# Group by JE — are these whole JEs of empty currency, or mixed within JE?
from collections import defaultdict
by_je = defaultdict(list)
for r in records:
    by_je[r.get("journalEntryId")].append(r)

mixed_jes = 0
all_empty_jes = 0
for je_id, lines in by_je.items():
    has_empty = any((r.get("currencyCode") or "") == "" for r in lines)
    has_clp = any(r.get("currencyCode") == "CLP" for r in lines)
    if has_empty and has_clp:
        mixed_jes += 1
    elif has_empty and not has_clp:
        all_empty_jes += 1

print(f"\nJEs that mix empty + CLP lines: {mixed_jes}")
print(f"JEs where ALL lines are empty-currency: {all_empty_jes}")

# Distribution by date / month
from collections import Counter
months = Counter(r.get("date", "")[:7] for r in empty)
print(f"\nMonthly distribution of empty lines (top 15):")
for m, n in months.most_common(15):
    print(f"  {m}: {n}")

# Sample descriptions
print("\n--- 10 sample empty-currency lines ---")
for r in empty[:10]:
    print({
        "date": r.get("date"),
        "je_num": r.get("journalEntryNumber"),
        "account": r.get("accountNumber"),
        "desc": (r.get("description") or "")[:60],
        "debit": r.get("debit"),
        "credit": r.get("credit"),
    })

# Are accounts of empty-currency lines distinctive?
accounts = Counter(r.get("accountNumber") for r in empty)
print(f"\nAccounts with empty currencyCode (top 10):")
for a, n in accounts.most_common(10):
    print(f"  {a}: {n}")
