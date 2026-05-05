# backend/scripts

Operational scripts that live alongside the backend service.

## `smoke_fava_edit_validator.py` — Story 9.0 smoke test

End-to-end check that the Fava edit-validator extension reverts invalid
beancount edits before they hit disk. Boots Fava in a subprocess against
[ledger/main.beancount](../../ledger/main.beancount), drives it via HTTP,
and asserts on the filesystem.

### Run locally

```bash
# From repo root, with the venv active:
python -m backend.scripts.smoke_fava_edit_validator
```

Expected output:

```
PASS  A — valid edit persisted  (~0.25s)
PASS  B — invalid edit reverted + logged  (~0.20s)
SKIP  C — covered by unit test test_fresh_import_lock_times_out_and_reverts

ALL SMOKE CASES PASSED
```

If a case fails, inspect `_smoke_fava.log` (Fava server stdout/stderr)
and the contents of `ledger/_meta/edit-revert-log.jsonl`.

### What it covers (vs. story AC)

| Case | AC covered                          | Mechanism                              |
|------|-------------------------------------|----------------------------------------|
| A    | AC1, AC4, AC6 (case A)              | PUT a benign comment edit              |
| B    | AC1, AC2, AC4, AC5, AC6 (case B)    | PUT an edit that breaks double-entry   |
| C    | AC3, AC6 (case C) — see unit tests  | `test_fresh_import_lock_times_out_*`   |

Case C is exercised by the unit suite because driving the lock-wait via
HTTP would require mutating extension constants from outside the Fava
process — the unit test does the same job in <1s without the round-trip.

### Local prerequisites

- `pip install -r backend/requirements.txt`
- `pip install beancount fava` (already pulled by the dev shell; not yet in
  `requirements.txt` because the validator/Fava live in the Render
  `laudus-fava` service image, not the backend service)
- A `bean-check`-clean ledger at `ledger/main.beancount`. The mock checked
  into the repo passes; replace with the F0 bootstrap output from Story 9.1
  when it lands.

### Manual smoke against Fava UI

For a fully manual reproduction:

1. `python -m fava.cli ledger/main.beancount`
2. Open the Editor for `manual/2026-04.beancount`.
3. Replace `65690.00 CLP` with `99999.00 CLP` and save.
4. Confirm:
   - File on disk reverts to its previous content
   - `ledger/_meta/edit-revert-log.jsonl` gains one JSON line
   - `ledger/_meta/last-revert-message.json` contains the revert message
5. Make a benign edit (add a trailing comment) and save → file should keep
   the new content; the message file should disappear.

### Troubleshooting

- **`bean-check` not found** — the validator shells out via
  `python -m beancount.scripts.check`, so any environment that has
  `beancount` installed in the same interpreter as Fava will work. The
  console-script `bean-check` itself is not required.
- **`The system cannot find the path specified`** on save — usually means
  `_meta/.snapshots/` was deleted while Fava was running. The extension
  recreates it on demand, so a fresh request fixes it.
- **Slow tests** — each unit test boots a Python subprocess for
  `bean-check`. Real runtime under Fava is ~0.15s per save.
