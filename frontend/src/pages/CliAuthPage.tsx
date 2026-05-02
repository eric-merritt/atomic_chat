import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../hooks/useTheme';
import { LoginPage } from './LoginPage';
import { ParticleCanvas } from '../components/atoms/ParticleCanvas';

// Inline SVGs — these aren't in the shared Icon set
const TerminalIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="4 17 10 11 4 5" />
    <line x1="12" y1="19" x2="20" y2="19" />
  </svg>
);

const CheckIcon = () => (
  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <polyline points="9 12 11 14 15 10" />
  </svg>
);

const XIcon = () => (
  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <line x1="15" y1="9" x2="9" y2="15" />
    <line x1="9" y1="9" x2="15" y2="15" />
  </svg>
);

type Status = 'idle' | 'approving' | 'approved' | 'denied' | 'error';

export function CliAuthPage() {
  const { authenticated } = useAuth();
  const { theme } = useTheme();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const [status, setStatus] = useState<Status>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Missing token — bad link
  if (!token) {
    return (
      <div className="h-screen flex items-center justify-center bg-[var(--bg-base)]" data-theme={theme.id}>
        <p className="text-[var(--danger)] text-sm font-mono">Invalid CLI auth link — missing token.</p>
      </div>
    );
  }

  // Not logged in — render the full login page; after login this component re-renders to the disclaimer
  if (!authenticated) return <LoginPage />;

  const handleApprove = async () => {
    setStatus('approving');
    try {
      const resp = await fetch('/api/auth/cli/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
        credentials: 'include',
      });
      if (resp.ok) {
        setStatus('approved');
      } else {
        const data = await resp.json();
        setErrorMsg(data.error ?? 'Approval failed');
        setStatus('error');
      }
    } catch {
      setErrorMsg('Network error');
      setStatus('error');
    }
  };

  const handleDeny = async () => {
    setStatus('approving');
    await fetch('/api/auth/cli/deny', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
      credentials: 'include',
    }).catch(() => {});
    setStatus('denied');
  };

  return (
    <div className="h-screen flex items-center justify-center bg-[var(--bg-base)]" data-theme={theme.id}>
      <ParticleCanvas theme={theme.id} />
      <div className="relative z-10 w-full max-w-sm mx-4">
        <div className="bg-[var(--glass-bg-solid)] backdrop-blur-xl border border-[var(--accent)] rounded-2xl p-8 shadow-[0_8px_32px_rgba(0,0,0,0.2)]">

          {status === 'approved' && (
            <div className="flex flex-col items-center gap-3 text-center">
              <span className="text-[var(--accent)]"><CheckIcon /></span>
              <h2 className="text-lg font-bold text-[var(--text)]">Access Granted</h2>
              <p className="text-sm text-[var(--text-muted)]">Return to your terminal — authentication is complete.</p>
            </div>
          )}

          {status === 'denied' && (
            <div className="flex flex-col items-center gap-3 text-center">
              <span className="text-[var(--danger)]"><XIcon /></span>
              <h2 className="text-lg font-bold text-[var(--text)]">Access Denied</h2>
              <p className="text-sm text-[var(--text-muted)]">CLI authentication was declined.</p>
            </div>
          )}

          {status === 'error' && (
            <div className="flex flex-col items-center gap-3 text-center">
              <span className="text-[var(--danger)]"><XIcon /></span>
              <h2 className="text-lg font-bold text-[var(--text)]">Something went wrong</h2>
              <p className="text-xs text-[var(--danger)]">{errorMsg}</p>
            </div>
          )}

          {(status === 'idle' || status === 'approving') && (
            <>
              <h1 className="text-xl font-bold text-[var(--text)] text-center mb-1 tracking-widest uppercase flex items-center justify-center gap-2">
                <span className="text-[var(--accent)]"><TerminalIcon /></span>
                CLI Access
              </h1>
              <p className="text-sm text-[var(--text-muted)] text-center mb-6">
                A terminal session is requesting access to your account.
              </p>

              <div className="bg-[var(--msg-user)] border border-[var(--glass-border)] rounded-lg p-3 mb-6 text-xs text-[var(--text-muted)] leading-relaxed">
                Only approve if you trust this computer and terminal session. This creates a new login session for the CLI — it expires after 24 hours.
              </div>

              <div className="flex gap-3">
                <button
                  onClick={handleDeny}
                  disabled={status === 'approving'}
                  className="flex-1 py-2.5 rounded-lg text-sm font-semibold border border-[var(--glass-border)] text-[var(--text-muted)] hover:border-[var(--danger)] hover:text-[var(--danger)] transition-all disabled:opacity-50 cursor-pointer"
                >
                  Deny
                </button>
                <button
                  onClick={handleApprove}
                  disabled={status === 'approving'}
                  className="flex-1 py-2.5 rounded-lg text-sm font-semibold bg-[var(--accent)] text-[var(--bg-base)] hover:brightness-110 transition-all disabled:opacity-50 cursor-pointer"
                >
                  {status === 'approving' ? '…' : 'Approve'}
                </button>
              </div>
            </>
          )}

        </div>
      </div>
    </div>
  );
}
