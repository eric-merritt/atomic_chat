import { useState, type ChangeEvent } from 'react';

interface AmountInputProps {
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}

/**
 * Atom: numeric input that only accepts positive numbers with up to 2 decimals.
 * Displays formatted on blur, raw on focus for editing.
 */
export function AmountInput({
  value,
  onChange,
  disabled = false,
  placeholder = '0.00',
  className = '',
}: AmountInputProps) {
  const [focused, setFocused] = useState(false);
  const [raw, setRaw] = useState('');

  const display = focused
    ? raw
    : value > 0
      ? value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : '';

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const v = e.target.value;
    // Allow digits, one dot, up to 2 decimals
    if (v === '' || /^\d*\.?\d{0,2}$/.test(v)) {
      setRaw(v);
      const num = parseFloat(v);
      onChange(isNaN(num) ? 0 : num);
    }
  }

  function handleFocus() {
    setFocused(true);
    setRaw(value > 0 ? String(value) : '');
  }

  function handleBlur() {
    setFocused(false);
    setRaw('');
  }

  return (
    <input
      type="text"
      inputMode="decimal"
      value={display}
      onChange={handleChange}
      onFocus={handleFocus}
      onBlur={handleBlur}
      disabled={disabled}
      placeholder={placeholder}
      className={`w-full bg-transparent text-right font-mono text-sm tabular-nums
        text-[var(--text)] placeholder:text-[var(--text-muted)] placeholder:opacity-30
        outline-none px-3 py-2 transition-colors
        disabled:opacity-20 disabled:cursor-not-allowed
        ${className}`}
    />
  );
}
