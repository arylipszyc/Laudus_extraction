// TypeScript types — exported from here as they are created

export type UserRole = 'owner' | 'contador'

export interface UserSession {
  email: string
  role: UserRole
}

export interface DataTypeSyncStatus {
  last_sync: string | null
}

export interface SyncRunStats {
  balance_sheet_added: number | null
  ledger_added: number | null
}

export interface SyncStatus {
  balance_sheet: DataTypeSyncStatus
  ledger: DataTypeSyncStatus
  job_status: 'idle' | 'running' | 'done' | 'failed'
  job_id: string | null
  error: string | null
  stats: SyncRunStats | null
}

// ── Dashboard types ──────────────────────────────────────────────────────────

export type Entity = 'EAG' | 'Jocelyn' | 'Jeannette' | 'Johanna' | 'Jael'
export type DatePreset = 'month' | 'quarter' | 'year' | 'custom'

export interface DashboardMeta {
  last_sync: string | null
}

export interface BalanceSheetRecord {
  account_id: number | string
  account_number: string
  account_name: string
  debit: number
  credit: number
  debit_balance: number
  credit_balance: number
  query_date: string
  is_latest: string
}

export interface BalanceSheetResponse {
  data: BalanceSheetRecord[]
  meta: DashboardMeta
}

// Ledger field names match the backend's actual JSON keys — do NOT rename
export interface LedgerEntryRecord {
  journalentryid: number | string
  journalentrynumber: number | string
  date: string
  accountnumber: string
  lineid: number | string
  description: string
  debit: number
  credit: number
  currencycode: string
  paritytomaincurrency: number
  periodo: string
  accountName: string   // from ledger_final enrichment (PlanCuentas account name)
  Categoria1: string    // top-level category from PlanCuentas (e.g. "Ingresos", "Gastos")
  Categoria2: string    // 2nd-level category from PlanCuentas
  Categoria3: string    // 3rd-level category from PlanCuentas
}

export interface LedgerEntriesResponse {
  data: LedgerEntryRecord[]
  meta: DashboardMeta
}
