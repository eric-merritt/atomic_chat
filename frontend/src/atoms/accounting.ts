/** Accounting domain types — shared across components and API layer. */

export interface AccountSummary {
  id: number;
  name: string;
  account_type: 'asset' | 'liability' | 'equity' | 'revenue' | 'expense';
  account_number: string | null;
  normal_balance: 'debit' | 'credit';
  is_active: boolean;
}

export interface JournalLine {
  account: string;
  debit: number;
  credit: number;
}

export interface JournalEntryDraft {
  date: string;
  memo: string;
  lines: JournalLine[];
}

export interface JournalEntryResult {
  journal_entry_id: number;
  date: string;
  memo: string;
  lines: {
    account: string;
    account_type: string;
    debit: string;
    credit: string;
    effect: string;
  }[];
  total_debits: string;
  total_credits: string;
}

export interface LedgerResult {
  ledger_id: number;
  name: string;
  currency: string;
  accounts_created: { name: string; type: string; normal_balance: string }[];
}

export interface ToolResponse<T = unknown> {
  status: 'success' | 'error';
  data: T;
  error: string;
}

/** Empty line factory */
export function emptyLine(): JournalLine {
  return { account: '', debit: 0, credit: 0 };
}

/** Compute whether the entry balances */
export function isBalanced(lines: JournalLine[]): boolean {
  const debits = lines.reduce((s, l) => s + (l.debit || 0), 0);
  const credits = lines.reduce((s, l) => s + (l.credit || 0), 0);
  return Math.abs(debits - credits) < 0.005 && debits > 0;
}

/** Format a number as currency string */
export function fmt(n: number): string {
  if (!n) return '';
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Normal balance label for account types */
export const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  asset: 'Asset',
  liability: 'Liability',
  equity: 'Equity',
  revenue: 'Revenue',
  expense: 'Expense',
};
