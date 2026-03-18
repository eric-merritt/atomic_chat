interface ApiKeyRowProps {
  id: string;
  prefix: string;
  label: string;
  createdAt: string;
  lastUsed: string | null;
  onRevoke: (id: string) => void;
}

export function ApiKeyRow({ id, prefix, label, createdAt, lastUsed, onRevoke }: ApiKeyRowProps) {
  return (
    <tr className="border-b border-[var(--glass-border)]">
      <td className="px-4 py-2 text-sm font-mono text-[var(--text)]">{prefix}...</td>
      <td className="px-4 py-2 text-sm text-[var(--text)]">{label}</td>
      <td className="px-4 py-2 text-xs text-[var(--text-muted)]">{new Date(createdAt).toLocaleDateString()}</td>
      <td className="px-4 py-2 text-xs text-[var(--text-muted)]">{lastUsed ? new Date(lastUsed).toLocaleDateString() : 'Never'}</td>
      <td className="px-4 py-2">
        <button onClick={() => onRevoke(id)} className="text-xs text-red-400 hover:text-red-300 cursor-pointer">Revoke</button>
      </td>
    </tr>
  );
}
