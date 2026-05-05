"""
Probe: confirm empirically what Laudus returns for a USD JE line.
Looking for: currencyCode, parityToMainCurrency, debit, credit on USD lines.
"""
import sys
sys.path.insert(0, r"c:\dev\bmad-workspace\LAUDUS_Backup")

from pipeline.services.ledger_service import fetch_ledger
from pipeline.config.laudus_config import LEDGER_URL

# Fetch last 90 days
import datetime
date_to = datetime.date.today()
date_from = datetime.date(2024, 1, 1)  # 2+ years back to find USD JEs

print(f"Fetching ledger {date_from} -> {date_to}...")
records = fetch_ledger(LEDGER_URL, params={"dateFrom": str(date_from), "dateTo": str(date_to), "accountNumberFrom": "1"})

if not records:
    print("No records returned.")
    sys.exit(1)

print(f"Total records: {len(records)}")

# Show distinct currencyCodes
from collections import Counter
codes = Counter(r.get("currencyCode") for r in records)
print(f"\ncurrencyCode distribution: {dict(codes)}")

# Show distinct parities
parities = Counter(r.get("parityToMainCurrency") for r in records)
print(f"\nDistinct parities (top 10): {parities.most_common(10)}")

# Find non-CLP examples
non_clp = [r for r in records if r.get("currencyCode") and r.get("currencyCode") != "CLP"]
print(f"\nNon-CLP lines: {len(non_clp)}")

if non_clp:
    print("\n=== Sample USD/foreign JE lines ===")
    for r in non_clp[:5]:
        print({
            "date": r.get("date"),
            "journalEntryNumber": r.get("journalEntryNumber"),
            "accountNumber": r.get("accountNumber"),
            "description": (r.get("description") or "")[:50],
            "currencyCode": r.get("currencyCode"),
            "parityToMainCurrency": r.get("parityToMainCurrency"),
            "debit": r.get("debit"),
            "credit": r.get("credit"),
        })
        # Check: is debit/credit consistent with CLP-already-converted hypothesis?
        # If debit looks like CLP-magnitude (e.g., 400000 for a 450 USD purchase at 950),
        # then debit IS in CLP. If debit looks like USD-magnitude (450), then debit IS in USD.
        debit = float(r.get("debit") or 0)
        credit = float(r.get("credit") or 0)
        parity = float(r.get("parityToMainCurrency") or 0)
        amount = debit if debit else credit
        if amount and parity:
            implied_usd = amount / parity
            implied_clp = amount * parity
            print(f"   amount={amount}, parity={parity}")
            print(f"   if amount-is-CLP: original USD = {implied_usd:.2f}")
            print(f"   if amount-is-USD: converted CLP = {implied_clp:.2f}")
        print()
