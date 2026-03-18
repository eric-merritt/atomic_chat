import { useState } from 'react';
import { Modal } from '../atoms/Modal';

interface CreateKeyModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export function CreateKeyModal({ open, onClose, onCreated }: CreateKeyModalProps) {
  const [label, setLabel] = useState('');
  const [rawKey, setRawKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleCreate = async () => {
    const resp = await fetch('/api/auth/keys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ label: label || 'Untitled' }),
    });
    const data = await resp.json();
    if (data.key) setRawKey(data.key);
  };

  const handleCopy = () => {
    if (rawKey) {
      navigator.clipboard.writeText(rawKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleClose = () => {
    setLabel('');
    setRawKey(null);
    setCopied(false);
    onClose();
    if (rawKey) onCreated();
  };

  return (
    <Modal open={open} onClose={handleClose}>
      <h3 className="text-lg font-semibold text-[var(--text)] mb-4">Create API Key</h3>
      {!rawKey ? (
        <div className="space-y-3">
          <input
            type="text"
            placeholder="Key label"
            value={label}
            onChange={e => setLabel(e.target.value)}
            className="w-full bg-[var(--input-bg)] text-[var(--text)] border border-[var(--glass-border)] rounded-lg px-4 py-2 text-sm font-mono outline-none focus:border-[var(--accent)]"
          />
          <button onClick={handleCreate} className="px-4 py-2 text-sm rounded-lg bg-[var(--accent)] text-white hover:opacity-90 cursor-pointer">
            Create
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-red-400">Store this key securely. It cannot be shown again.</p>
          <div className="bg-[var(--input-bg)] border border-[var(--glass-border)] rounded-lg p-3 font-mono text-xs text-[var(--text)] break-all">
            {rawKey}
          </div>
          <button onClick={handleCopy} className="px-4 py-2 text-sm rounded-lg bg-[var(--accent)] text-white hover:opacity-90 cursor-pointer">
            {copied ? 'Copied!' : 'Copy Key'}
          </button>
        </div>
      )}
    </Modal>
  );
}
