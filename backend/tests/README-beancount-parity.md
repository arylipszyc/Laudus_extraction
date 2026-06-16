# Beancount ↔ Sheets parity suite (Story 9.2 AC9)

`test_beancount_parity.py` guards that the Beancount engine (BQL) produces
responses the frontend cannot distinguish from the legacy Sheets path.

## Two layers

1. **Structural parity — runs in the normal suite.**
   The BQL output keys match the Pydantic API models (`BalanceSheetRecord`,
   `LedgerEntryRecord`) exactly, and every record validates against them. This
   is the contract that protects the frontend from visual regression during the
   migration and is enforced today against a synthetic mini-ledger.

2. **Value parity — `xfail` until the ledger is bootstrapped.**
   Amount-for-amount comparison against the real Laudus-derived Sheets snapshot
   cannot run yet: the ledger only contains opening balances + the chart of
   accounts. The transactional data arrives with the **Laudus importer (Story
   9.4)**. Until then `test_value_parity_*` is `xfail` (non-strict) by design.

## Running just this suite

```bash
PYTHONUTF8=1 python -m pytest backend/tests/test_beancount_parity.py -m beancount_parity
```

The `beancount_parity` marker lets CI run or skip these independently of the
fast unit suite.

## When Story 9.4 lands

1. Bootstrap the ledger (Laudus importer writes `ledger/imports/laudus/*.beancount`).
2. Capture a Sheets snapshot for the same `(entity, date_range)` fixtures
   (full-year EAG 2024, Q1 2025 EAG, full-year Jocelyn 2024).
3. Replace the `xfail` body with the real comparison:
   structural `assertEqual` on keys/order/dates, `assertAlmostEqual` on amounts.
4. Log any amount discrepancies (account, Sheets value, Beancount value, diff) —
   a non-zero diff may legitimately mean Sheets had a bug the ledger fixes; the
   SHAPE must never differ.
