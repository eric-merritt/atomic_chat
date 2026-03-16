interface SelectOption {
  value: string;
  label: string;
  group?: string;
}

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  className?: string;
}

export function Select({ value, onChange, options, className = '' }: SelectProps) {
  const groups = new Map<string | undefined, SelectOption[]>();
  for (const opt of options) {
    const key = opt.group;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(opt);
  }

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`bg-[var(--glass-bg)] text-[var(--text)] border border-[var(--glass-border)] rounded-lg px-3 py-1.5 text-sm cursor-pointer outline-none ${className}`}
    >
      {[...groups.entries()].map(([group, opts]) =>
        group ? (
          <optgroup key={group} label={group}>
            {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </optgroup>
        ) : (
          opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)
        )
      )}
    </select>
  );
}
