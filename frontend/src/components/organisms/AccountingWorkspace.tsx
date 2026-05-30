import { useState, useEffect, useCallback } from 'react';
import { useWorkspace } from '../../hooks/useWorkspace';
import { JournalEntryForm } from './JournalEntryForm';
import { Button } from '../atoms/Button';
import { fetchAccounts, fetchTrialBalance } from '../../api/accounting';
import type { AccountSummary } from '../../atoms/accounting';

type Tab = 'journal' | 'accounts' | 'trial-balance';

const TABS: { id: Tab; label: string }[] = [
  { id: 'journal',       label: 'Journal Entry' },
  { id: 'accounts',      label: 'Accounts' },
  { id: 'trial-balance', label: 'Trial Balance' },
];

// ── Accounts panel ────────────────────────────────────────────

const TYPE_COLORS: Record<string, string> = {
  asset:     'text-emerald-400',
  liability: 'text-rose-400',
  equity:    'text-violet-400',
  revenue:   'text-sky-400',
  expense:   'text-amber-400',
};

function AccountsPanel() {
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchAccounts().then((r) => {
      if (r.status === 'success') setAccounts(r.data.accounts);
      else setError(r.error || 'Failed to load accounts');
      setLoading(false);
    });
  }, []);

  if (loading) return <Spinner label="Loading accounts..." />;
  if (error)   return <ErrorMsg msg={error} />;
  if (!accounts.length) return <Empty msg="No accounts. Create a ledger first." />;

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse font-mono text-xs">
        <thead>
          <tr className="border-b-2 border-[var(--accent)]">
            {['Account', 'Type', 'Normal', '#'].map((h) => (
              <th key={h} className="text-left text-[10px] uppercase tracking-[0.2em]
                text-[var(--text-muted)] px-3 py-2 font-normal">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {accounts.map((a) => (
            <tr key={a.id} className="border-b border-[var(--glass-border)]
              hover:bg-[var(--glass-highlight)] transition-colors">
              <td className="px-3 py-2 text-[var(--text)]">{a.name}</td>
              <td className={`px-3 py-2 capitalize ${TYPE_COLORS[a.account_type] ?? 'text-[var(--text-muted)]'}`}>
                {a.account_type}
              </td>
              <td className="px-3 py-2 text-[var(--text-muted)] capitalize">{a.normal_balance}</td>
              <td className="px-3 py-2 text-[var(--text-muted)]">{a.account_number ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Trial balance panel ───────────────────────────────────────

interface TBLine { account: string; account_type: string; debit: string; credit: string }

function TrialBalancePanel() {
  const [rows, setRows] = useState<TBLine[]>([]);
  const [totals, setTotals] = useState({ debits: '0.00', credits: '0.00' });
  const [asOf, setAsOf] = useState(() => new Date().toISOString().slice(0, 10));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback((date: string) => {
    setLoading(true);
    fetchTrialBalance(date).then((r) => {
      if (r.status === 'success') {
        const d = r.data as Record<string, unknown>;
        setRows((d.accounts as TBLine[]) ?? []);
        setTotals({
          debits:  (d.total_debits  as string) ?? '0.00',
          credits: (d.total_credits as string) ?? '0.00',
        });
      } else {
        setError(r.error || 'Failed to load trial balance');
      }
      setLoading(false);
    });
  }, []);

  useEffect(() => { load(asOf); }, [load, asOf]);

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-[var(--text-muted)]">
          As of
        </span>
        <input
          type="date"
          value={asOf}
          onChange={(e) => setAsOf(e.target.value)}
          className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded
            px-2 py-1 text-xs font-mono text-[var(--text)] focus:outline-none
            focus:border-[var(--accent)]"
        />
        <Button variant="ghost" onClick={() => load(asOf)}>Refresh</Button>
      </div>

      {loading ? <Spinner label="Loading..." /> : error ? <ErrorMsg msg={error} /> : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse font-mono text-xs">
            <thead>
              <tr className="border-b-2 border-[var(--accent)]">
                {['Account', 'Debit', 'Credit'].map((h) => (
                  <th key={h} className={`text-[10px] uppercase tracking-[0.2em]
                    text-[var(--text-muted)] px-3 py-2 font-normal
                    ${h === 'Account' ? 'text-left' : 'text-right'}`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-b border-[var(--glass-border)]
                  hover:bg-[var(--glass-highlight)] transition-colors">
                  <td className="px-3 py-2 text-[var(--text)]">{row.account}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-[var(--text)]">
                    {row.debit !== '0.00' ? row.debit : ''}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-[var(--text)]">
                    {row.credit !== '0.00' ? row.credit : ''}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-[var(--accent)]">
                <td className="px-3 py-2 text-right text-[10px] uppercase tracking-[0.2em]
                  text-[var(--text-muted)]">
                  Totals
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-[var(--text)]">
                  {totals.debits}
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-[var(--text)]">
                  {totals.credits}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Shared helpers ────────────────────────────────────────────

const Spinner = ({ label }: { label: string }) => (
  <div className="flex items-center justify-center py-12 text-[var(--text-muted)] text-xs font-mono">
    {label}
  </div>
);

const ErrorMsg = ({ msg }: { msg: string }) => (
  <div className="px-3 py-2 rounded-lg border border-[var(--danger)]
    text-[var(--danger)] text-xs font-mono mt-4">
    {msg}
  </div>
);

const Empty = ({ msg }: { msg: string }) => (
  <div className="flex items-center justify-center py-12 text-[var(--text-muted)] text-xs font-mono">
    {msg}
  </div>
);

// ── AccountingWorkspace ───────────────────────────────────────

export function AccountingWorkspace() {
  const { closeAccounting } = useWorkspace();
  const [tab, setTab] = useState<Tab>('journal');

  return (
    <div className="flex flex-col h-full overflow-hidden bg-[var(--bg-base)]">

      {/* Top bar: back + title + tabs */}
      <div className="border-b border-[var(--glass-border)] bg-[var(--glass-bg-solid)]">

        {/* Header row */}
        <div className="flex items-center gap-3 px-4 pt-3 pb-1">
          <button
            onClick={closeAccounting}
            className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[var(--accent)]
              transition-colors cursor-pointer shrink-0"
            title="Back to tools"
          >
            ← Back
          </button>
          <span className="font-mono text-xs uppercase tracking-[0.25em] text-[var(--accent)]">
            Ledger
          </span>
        </div>

        {/* Tab strip */}
        <div className="flex gap-0 px-4">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`text-[10px] font-mono uppercase tracking-[0.2em] px-3 py-2
                border-b-2 transition-colors cursor-pointer
                ${tab === id
                  ? 'border-[var(--accent)] text-[var(--accent)]'
                  : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text)]'
                }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-4">
        {tab === 'journal'       && <JournalEntryForm />}
        {tab === 'accounts'      && <AccountsPanel />}
        {tab === 'trial-balance' && <TrialBalancePanel />}
      </div>
    </div>
  );
}
