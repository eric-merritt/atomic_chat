import { useState, useEffect, useCallback } from 'react';
import { JournalLineRow } from '../molecules/JournalLineRow';
import { Button } from '../atoms/Button';
import { Input } from '../atoms/Input';
import type { AccountSummary, JournalLine, JournalEntryResult } from '../../atoms/accounting';
import { emptyLine, isBalanced, fmt } from '../../atoms/accounting';
import { fetchAccounts, postJournalEntry } from '../../api/accounting';

interface JournalEntryFormProps {
  onSuccess?: (result: JournalEntryResult) => void;
}

/**
 * Organism: full journal entry form — date, memo, N debit/credit lines, submit.
 * Manages all form state; calls accounting API on submit.
 */
export function JournalEntryForm({ onSuccess }: JournalEntryFormProps) {
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [noLedger, setNoLedger] = useState(false);

  // Form state
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [memo, setMemo] = useState('');
  const [lines, setLines] = useState<JournalLine[]>([emptyLine(), emptyLine()]);

  // Load accounts
  const loadAccounts = useCallback(async () => {
    setLoading(true);
    const resp = await fetchAccounts();
    if (resp.status === 'success' && resp.data) {
      setAccounts(resp.data.accounts);
      setNoLedger(false);
    } else if (resp.error?.includes('No ledger')) {
      setNoLedger(true);
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadAccounts(); }, [loadAccounts]);

  // Computed
  const totalDebits = lines.reduce((s, l) => s + (l.debit || 0), 0);
  const totalCredits = lines.reduce((s, l) => s + (l.credit || 0), 0);
  const balanced = isBalanced(lines);
  const diff = Math.abs(totalDebits - totalCredits);
  const hasEmptyAccounts = lines.some((l) => !l.account);
  const canSubmit = balanced && !hasEmptyAccounts && memo.trim() !== '' && !submitting;

  function handleLineChange(index: number, field: keyof JournalLine, value: string | number) {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, [field]: value } : l)));
    setError('');
    setSuccess('');
  }

  function handleRemoveLine(index: number) {
    setLines((prev) => prev.filter((_, i) => i !== index));
  }

  function handleAddLine() {
    setLines((prev) => [...prev, emptyLine()]);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setError('');
    setSuccess('');

    const resp = await postJournalEntry({ date, memo, lines });

    if (resp.status === 'success') {
      setSuccess(`Entry #${resp.data.journal_entry_id} recorded.`);
      setMemo('');
      setLines([emptyLine(), emptyLine()]);
      onSuccess?.(resp.data);
    } else {
      setError(resp.error || 'Failed to record entry.');
    }
    setSubmitting(false);
  }

  function handleReset() {
    setMemo('');
    setLines([emptyLine(), emptyLine()]);
    setError('');
    setSuccess('');
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-[var(--text-muted)] text-sm font-mono">
        Loading accounts...
      </div>
    );
  }

  if (noLedger) {
    return (
      <div className="max-w-lg mx-auto py-20 text-center">
        <p className="text-[var(--text-secondary)] text-sm mb-4">
          No ledger found. Create one to start recording journal entries.
        </p>
        <Button variant="primary" onClick={() => {
          // TODO: wire to createLedger API
          import('../../api/accounting').then(({ createLedger }) =>
            createLedger().then(() => loadAccounts())
          );
        }}>
          Create Ledger
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-3xl mx-auto">
      {/* Title bar */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-[var(--text)] text-lg font-mono font-light tracking-wider uppercase">
          General Journal
        </h2>
        <span className="text-[var(--text-muted)] text-xs font-mono tracking-widest">
          DOUBLE-ENTRY
        </span>
      </div>

      {/* Date + Memo row */}
      <div className="flex gap-3 mb-4">
        <Input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="!w-44 !flex-none font-mono"
        />
        <Input
          value={memo}
          onChange={(e) => setMemo(e.target.value)}
          placeholder="Transaction memo..."
          className="flex-1"
        />
      </div>

      {/* Ledger table */}
      <div className="border border-[var(--glass-border)] rounded-lg overflow-hidden
        bg-[var(--glass-bg)] backdrop-blur-sm">

        {/* Header */}
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b-2 border-[var(--accent)] text-[var(--text-muted)]">
              <th className="text-left text-[10px] font-mono font-normal uppercase tracking-[0.2em]
                px-3 py-2.5 border-r border-[var(--glass-border)]">
                Account
              </th>
              <th className="text-right text-[10px] font-mono font-normal uppercase tracking-[0.2em]
                px-3 py-2.5 w-32 border-r border-[var(--glass-border)]">
                Debit
              </th>
              <th className="text-right text-[10px] font-mono font-normal uppercase tracking-[0.2em]
                px-3 py-2.5 w-32 border-r border-[var(--glass-border)]">
                Credit
              </th>
              <th className="w-10" />
            </tr>
          </thead>

          <tbody>
            {lines.map((line, i) => (
              <JournalLineRow
                key={i}
                line={line}
                index={i}
                accounts={accounts}
                onChange={handleLineChange}
                onRemove={handleRemoveLine}
                canRemove={lines.length > 2}
              />
            ))}
          </tbody>

          {/* Totals */}
          <tfoot>
            <tr className="border-t-2 border-[var(--accent)]">
              <td className="px-3 py-2 text-right text-[10px] font-mono uppercase tracking-[0.2em]
                text-[var(--text-muted)] border-r border-[var(--glass-border)]">
                Totals
              </td>
              <td className={`px-3 py-2 text-right font-mono text-sm tabular-nums
                border-r border-[var(--glass-border)]
                ${balanced ? 'text-[var(--success)]' : 'text-[var(--text)]'}`}>
                {totalDebits > 0 ? fmt(totalDebits) : ''}
              </td>
              <td className={`px-3 py-2 text-right font-mono text-sm tabular-nums
                border-r border-[var(--glass-border)]
                ${balanced ? 'text-[var(--success)]' : 'text-[var(--text)]'}`}>
                {totalCredits > 0 ? fmt(totalCredits) : ''}
              </td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>

      {/* Balance indicator */}
      {totalDebits > 0 && totalCredits > 0 && !balanced && (
        <div className="mt-2 text-right text-xs font-mono text-[var(--danger)] opacity-80">
          Off by {fmt(diff)} — debits must equal credits
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-between mt-4 gap-3">
        <button
          type="button"
          onClick={handleAddLine}
          className="text-[var(--accent)] text-xs font-mono tracking-wider uppercase
            hover:text-[var(--accent-hover)] transition-colors cursor-pointer"
        >
          + Add line
        </button>

        <div className="flex gap-2">
          <Button variant="ghost" type="button" onClick={handleReset}>
            Clear
          </Button>
          <Button variant="primary" type="submit" disabled={!canSubmit}>
            {submitting ? 'Recording...' : 'Record Entry'}
          </Button>
        </div>
      </div>

      {/* Feedback */}
      {error && (
        <div className="mt-3 px-3 py-2 rounded-lg bg-[var(--danger)] bg-opacity-10
          border border-[var(--danger)] text-[var(--danger)] text-xs font-mono">
          {error}
        </div>
      )}
      {success && (
        <div className="mt-3 px-3 py-2 rounded-lg bg-[var(--success)] bg-opacity-10
          border border-[var(--success)] text-[var(--success)] text-xs font-mono">
          {success}
        </div>
      )}
    </form>
  );
}
