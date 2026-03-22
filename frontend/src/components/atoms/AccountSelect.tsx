import type { AccountSummary } from '../../atoms/accounting';
import { ACCOUNT_TYPE_LABELS } from '../../atoms/accounting';

interface AccountSelectProps {
  value: string;
  onChange: (name: string) => void;
  accounts: AccountSummary[];
  placeholder?: string;
  indent?: boolean;
  className?: string;
}

/**
 * Atom: account name picker grouped by account type.
 * Uses the same glass styling as the project's Select atom.
 */
export function AccountSelect({
  value,
  onChange,
  accounts,
  placeholder = 'Select account...',
  indent = false,
  className = '',
}: AccountSelectProps) {
  // Group by type
  const groups = new Map<string, AccountSummary[]>();
  for (const a of accounts) {
    if (!a.is_active) continue;
    const key = a.account_type;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(a);
  }

  const typeOrder = ['asset', 'liability', 'equity', 'revenue', 'expense'];

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`w-full bg-transparent text-[var(--text)] text-sm font-light
        outline-none cursor-pointer appearance-none px-3 py-2
        ${indent ? 'pl-8' : ''}
        ${!value ? 'text-[var(--text-muted)] opacity-50' : ''}
        ${className}`}
    >
      <option value="">{placeholder}</option>
      {typeOrder.map((type) => {
        const accts = groups.get(type);
        if (!accts) return null;
        return (
          <optgroup key={type} label={ACCOUNT_TYPE_LABELS[type]}>
            {accts.map((a) => (
              <option key={a.name} value={a.name}>
                {a.account_number ? `${a.account_number} — ${a.name}` : a.name}
              </option>
            ))}
          </optgroup>
        );
      })}
    </select>
  );
}
