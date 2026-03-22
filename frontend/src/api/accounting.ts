/** API calls for accounting tools — invoked via chat stream endpoint. */

import type {
  AccountSummary,
  JournalEntryDraft,
  JournalEntryResult,
  LedgerResult,
  ToolResponse,
} from '../atoms/accounting';

const CREDS: RequestInit = { credentials: 'include' };
const POST = (body: object): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
  credentials: 'include',
});

/**
 * All accounting operations go through the chat stream as tool calls.
 * But for the direct journal UI, we call the Flask backend which
 * invokes the tool functions server-side and returns the tool_result JSON.
 *
 * These hit /api/accounting/* endpoints (we'll add a thin Flask route).
 * Fallback: post a structured message through /api/chat/stream.
 */

export async function fetchAccounts(): Promise<ToolResponse<{ count: number; accounts: AccountSummary[] }>> {
  try {
    const resp = await fetch('/api/accounting/accounts', CREDS);
    if (!resp.ok) return { status: 'error', data: { count: 0, accounts: [] }, error: `HTTP ${resp.status}` };
    return resp.json();
  } catch (e) {
    return { status: 'error', data: { count: 0, accounts: [] }, error: String(e) };
  }
}

export async function createLedger(name: string = 'My Ledger'): Promise<ToolResponse<LedgerResult>> {
  try {
    const resp = await fetch('/api/accounting/ledger', POST({ name }));
    if (!resp.ok) return { status: 'error', data: null as unknown as never, error: `HTTP ${resp.status}` };
    return resp.json();
  } catch (e) {
    return { status: 'error', data: null as unknown as never, error: String(e) };
  }
}

export async function postJournalEntry(entry: JournalEntryDraft): Promise<ToolResponse<JournalEntryResult>> {
  try {
    const resp = await fetch('/api/accounting/journal', POST(entry));
    if (!resp.ok) return { status: 'error', data: null as unknown as never, error: `HTTP ${resp.status}` };
    return resp.json();
  } catch (e) {
    return { status: 'error', data: null as unknown as never, error: String(e) };
  }
}

export async function fetchTrialBalance(asOfDate?: string): Promise<ToolResponse> {
  try {
    const url = asOfDate
      ? `/api/accounting/trial-balance?as_of_date=${asOfDate}`
      : '/api/accounting/trial-balance';
    const resp = await fetch(url, CREDS);
    if (!resp.ok) return { status: 'error', data: null, error: `HTTP ${resp.status}` };
    return resp.json();
  } catch (e) {
    return { status: 'error', data: null, error: String(e) };
  }
}
