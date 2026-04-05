# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Synchronizes accounting data (Balance Sheet and General Ledger) from the **Laudus ERP API** into **Google Sheets**. It supports incremental syncs (new records only) and bulk historical backfills, with duplicate prevention via in-memory upsert keyed on primary key fields.

## Running the Project

```bash
# Install dependencies
pip install -r requirements.txt

# Incremental sync (runs balance sheet + ledger for recent dates)
python sync.py

# One-time bulk historical load (Jan 2021 → present)
python backfill_data.py

# Test Google Sheets connectivity
python test_gspread.py
```

No test framework is configured. Manual validation is done via `test_gspread.py`.

## Environment Setup

Create a `.env` file in the project root with:

```
LAUDUS_USERNAME=...
LAUDUS_PASSWORD=...
LAUDUS_COMPANYVATID=...
GOOGLE_APPLICATION_CREDENTIALS=config/serviceAccountKey.json
GOOGLE_SHEET_ID=...
```

Place the Google Service Account JSON at `config/serviceAccountKey.json`. The target Google Sheet must be shared with the service account email.

## Architecture

The project uses a layered architecture:

```
sync.py / backfill_data.py      ← Orchestrators (entry points)
        │
        ├── config/
        │   ├── laudus_config.py    ← Laudus API credentials + endpoint builder
        │   └── gspread_config.py   ← Google Sheets client initialization
        │
        ├── services/
        │   ├── laudus_service.py       ← HTTP client: token cache, auto-retry on 401
        │   ├── balance_sheet_service.py ← Balance sheet endpoint wrapper
        │   └── ledger_service.py       ← Ledger endpoint wrapper
        │
        └── utils/
            ├── dates.py           ← Month-end date calculations, incremental ranges
            └── gspread_utils.py   ← In-memory upsert logic (download → merge → clear → upload)
```

### Key Design Decisions

**Token management** (`services/laudus_service.py`): Token is requested lazily on first call and cached globally. On any 401 response, the token is cleared and the request is retried once.

**Upsert logic** (`utils/gspread_utils.py`): Reads all existing rows from a sheet, builds an in-memory dict keyed by a caller-provided primary key function, merges new records (overwriting on key collision), then clears and batch-uploads the full dataset. Uses `USER_ENTERED` input mode to preserve numeric and date types.

**Sync tracking**: A `date_range` worksheet stores the last synced `dateTo`. On each incremental run, `sync.py` reads this value and sets `dateFrom = last_date + 1 day`. If `dateFrom > today`, the sync is skipped.

**Primary keys used:**
- Balance Sheet: `{account_id}_{query_date}`
- Ledger: `{journalentryid}_{lineid}`

**`is_latest` flag**: After every balance sheet upsert, the code recalculates which `query_date` is the most recent per account and sets `is_latest = TRUE` only for those rows.
