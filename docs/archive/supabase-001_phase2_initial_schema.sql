-- Migration 001: Phase 2 initial schema
-- Run this in the Supabase SQL editor or via supabase CLI

-- Chart of accounts synced from Google Sheets (source of truth remains Sheets)
CREATE TABLE IF NOT EXISTS plan_de_cuentas (
  account_number  VARCHAR PRIMARY KEY,
  account_name    VARCHAR NOT NULL,
  account_type    VARCHAR,
  cat1            VARCHAR,
  cat2            VARCHAR,
  cat3            VARCHAR,
  active          BOOLEAN DEFAULT true,
  synced_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Bank account registry — maps real bank accounts to chart of accounts
-- UNIQUE on account_number: one bank_accounts row per plan_de_cuentas entry
CREATE TABLE IF NOT EXISTS bank_accounts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_number   VARCHAR NOT NULL UNIQUE REFERENCES plan_de_cuentas(account_number),
  account_type     VARCHAR NOT NULL,
  account_currency VARCHAR NOT NULL,
  bank_name        VARCHAR,
  active           BOOLEAN DEFAULT true
);

-- One record per uploaded credit card statement
CREATE TABLE IF NOT EXISTS cartola_batches (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity                 VARCHAR NOT NULL DEFAULT 'EAG',
  account_name           VARCHAR NOT NULL,
  bank                   VARCHAR,
  period                 DATE NOT NULL,
  currency               VARCHAR NOT NULL,
  opening_balance        DECIMAL,
  closing_balance        DECIMAL,
  sum_transactions       DECIMAL,
  balance_discrepancy    DECIMAL,
  laudus_entry_id        VARCHAR,
  laudus_payment_amount  DECIMAL,
  status                 VARCHAR NOT NULL DEFAULT 'extracted',
  override_justification TEXT,
  uploaded_by            VARCHAR NOT NULL,
  uploaded_at            TIMESTAMPTZ DEFAULT NOW(),
  extraction_model       VARCHAR
);

-- One record per transaction line in a statement
CREATE TABLE IF NOT EXISTS cartola_transactions (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id           UUID NOT NULL REFERENCES cartola_batches(id) ON DELETE CASCADE,
  date               DATE NOT NULL,
  description        TEXT NOT NULL,
  amount             DECIMAL NOT NULL,
  currency           VARCHAR NOT NULL,
  category_auto      VARCHAR,
  category_confirmed VARCHAR,
  category_status    VARCHAR NOT NULL DEFAULT 'pending',
  match_source       VARCHAR,
  reviewed_by        VARCHAR,
  reviewed_at        TIMESTAMPTZ
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_cartola_batches_account_period
  ON cartola_batches (account_name, period);

CREATE INDEX IF NOT EXISTS idx_cartola_transactions_batch
  ON cartola_transactions (batch_id);

CREATE INDEX IF NOT EXISTS idx_cartola_transactions_status
  ON cartola_transactions (category_status);

CREATE INDEX IF NOT EXISTS idx_bank_accounts_number
  ON bank_accounts (account_number);
