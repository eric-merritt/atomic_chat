import { useState, useEffect, useCallback } from 'react';
import { ApiKeyRow } from '../molecules/ApiKeyRow';
import { CreateKeyModal } from '../molecules/CreateKeyModal';

interface ApiKey {
  id: string;
  prefix: string;
  label: string;
  created_at: string;
  last_used: string | null;
}

export function ApiKeyPanel() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    const resp = await fetch('/api/auth/keys', { credentials: 'include' });
    const data = await resp.json();
    setKeys(data.keys || []);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleRevoke = async (id: string) => {
    await fetch(`/api/auth/keys/${id}`, { method: 'DELETE', credentials: 'include' });
    load();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-[var(--text)]">API Keys</h2>
        <button onClick={() => setShowCreate(true)}
          className="px-4 py-2 text-sm rounded-lg bg-[var(--accent)] text-white hover:opacity-90 cursor-pointer">
          Create Key
        </button>
      </div>
      {keys.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">No API keys yet.</p>
      ) : (
        <table className="w-full">
          <thead>
            <tr className="border-b border-[var(--glass-border)]">
              <th className="px-4 py-2 text-left text-xs text-[var(--text-muted)]">Prefix</th>
              <th className="px-4 py-2 text-left text-xs text-[var(--text-muted)]">Label</th>
              <th className="px-4 py-2 text-left text-xs text-[var(--text-muted)]">Created</th>
              <th className="px-4 py-2 text-left text-xs text-[var(--text-muted)]">Last Used</th>
              <th className="px-4 py-2 text-left text-xs text-[var(--text-muted)]"></th>
            </tr>
          </thead>
          <tbody>
            {keys.map(k => (
              <ApiKeyRow
                key={k.id}
                id={k.id}
                prefix={k.prefix}
                label={k.label}
                createdAt={k.created_at}
                lastUsed={k.last_used}
                onRevoke={handleRevoke}
              />
            ))}
          </tbody>
        </table>
      )}
      <CreateKeyModal open={showCreate} onClose={() => setShowCreate(false)} onCreated={load} />
    </div>
  );
}
