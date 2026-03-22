import { AmountInput } from '../atoms/AmountInput';
import { AccountSelect } from '../atoms/AccountSelect';
import type { AccountSummary, JournalLine } from '../../atoms/accounting';

interface JournalLineRowProps {
  line: JournalLine;
  index: number;
  accounts: AccountSummary[];
  onChange: (index: number, field: keyof JournalLine, value: string | number) => void;
  onRemove: (index: number) => void;
  canRemove: boolean;
}

/**
 * Molecule: one row of a journal entry — account picker + debit + credit.
 * Second and subsequent rows indent the account name (accounting convention).
 */
export function JournalLineRow({
  line,
  index,
  accounts,
  onChange,
  onRemove,
  canRemove,
}: JournalLineRowProps) {
  const isCredit = index > 0;

  function handleDebit(v: number) {
    onChange(index, 'debit', v);
    if (v > 0) onChange(index, 'credit', 0);
  }

  function handleCredit(v: number) {
    onChange(index, 'credit', v);
    if (v > 0) onChange(index, 'debit', 0);
  }

  return (
    <tr
      className={`group border-b border-[var(--glass-border)] transition-colors
        hover:bg-[var(--glass-highlight)]
        ${isCredit ? 'bg-transparent' : ''}`}
    >
      {/* Account */}
      <td className="border-r border-[var(--glass-border)]">
        <AccountSelect
          value={line.account}
          onChange={(v) => onChange(index, 'account', v)}
          accounts={accounts}
          indent={isCredit}
          placeholder={isCredit ? '    Account name...' : 'Account name...'}
        />
      </td>

      {/* Debit */}
      <td className="border-r border-[var(--glass-border)] w-32">
        <AmountInput
          value={line.debit}
          onChange={handleDebit}
          placeholder={!isCredit ? '0.00' : ''}
        />
      </td>

      {/* Credit */}
      <td className="border-r border-[var(--glass-border)] w-32">
        <AmountInput
          value={line.credit}
          onChange={handleCredit}
          placeholder={isCredit ? '0.00' : ''}
        />
      </td>

      {/* Remove */}
      <td className="w-10 text-center">
        {canRemove && (
          <button
            type="button"
            onClick={() => onRemove(index)}
            className="opacity-0 group-hover:opacity-60 hover:!opacity-100
              text-[var(--danger)] transition-opacity cursor-pointer text-xs"
            title="Remove line"
          >
            ✕
          </button>
        )}
      </td>
    </tr>
  );
}
