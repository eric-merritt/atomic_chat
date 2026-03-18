import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { oauthRedirect } from '../api/auth';
import { ParticleCanvas } from '../components/atoms/ParticleCanvas';
import { Icon } from '../components/atoms/Icon';
import { useTheme } from '../hooks/useTheme';

export function LoginPage() {
  const { login, register, error } = useAuth();
  const { theme } = useTheme();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const displayError = localError || error;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    setSubmitting(true);

    let err: string | null;
    if (mode === 'login') {
      err = await login(username, password);
    } else {
      if (password.length < 8) {
        setLocalError('Password must be at least 8 characters');
        setSubmitting(false);
        return;
      }
      err = await register(username, email, password);
    }
    if (err) setLocalError(err);
    setSubmitting(false);
  };

  return (
    <div className="h-screen flex items-center justify-center bg-[var(--bg-base)]" data-theme={theme.id}>
      <ParticleCanvas theme={theme.id} />
      <div className="relative z-10 w-full max-w-sm mx-4">
        <div className="bg-[var(--glass-bg-solid)] backdrop-blur-xl border border-[var(--accent)] rounded-2xl p-8 shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
          <h1 className="text-2xl font-bold text-[var(--text)] text-center mb-1 tracking-widest uppercase flex items-center justify-center">
            AT<Icon name="atom" size={24} className="inline-block mx-[-1px]" />MIC CHAT
          </h1>
          <p className="text-sm text-[var(--text-muted)] text-center mb-6">
            {mode === 'login' ? 'Sign in to continue' : 'Create an account'}
          </p>

          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <input
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-[var(--input-bg)] text-[var(--text)] border border-[var(--glass-border)] rounded-lg px-4 py-2.5 text-sm font-mono outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_2px_var(--accent-glow)] transition-all placeholder:text-[var(--text-muted)]"
              autoFocus
              required
            />
            {mode === 'register' && (
              <input
                type="email"
                placeholder="Email (optional)"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-[var(--input-bg)] text-[var(--text)] border border-[var(--glass-border)] rounded-lg px-4 py-2.5 text-sm font-mono outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_2px_var(--accent-glow)] transition-all placeholder:text-[var(--text-muted)]"
              />
            )}
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-[var(--input-bg)] text-[var(--text)] border border-[var(--glass-border)] rounded-lg px-4 py-2.5 text-sm font-mono outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_2px_var(--accent-glow)] transition-all placeholder:text-[var(--text-muted)]"
              required
            />

            {displayError && (
              <p className="text-xs text-[var(--danger)] text-center">{displayError}</p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full py-2.5 rounded-lg text-sm font-semibold bg-[var(--accent)] text-[var(--bg-base)] hover:brightness-110 transition-all disabled:opacity-50 cursor-pointer"
            >
              {submitting ? '...' : mode === 'login' ? 'Sign In' : 'Create Account'}
            </button>
          </form>

          <div className="flex items-center gap-3 mt-4">
            <div className="flex-1 border-t border-[var(--glass-border)]" />
            <span className="text-xs text-[var(--text-muted)]">or</span>
            <div className="flex-1 border-t border-[var(--glass-border)]" />
          </div>

          <div className="flex flex-col gap-2 mt-4">
            <button
              type="button"
              onClick={() => oauthRedirect('github')}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium border border-[var(--glass-border)] text-[var(--text)] hover:border-[var(--accent)] hover:bg-[var(--msg-user)] transition-all cursor-pointer"
            >
              <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/></svg>
              Continue with GitHub
            </button>
            <button
              type="button"
              onClick={() => oauthRedirect('google')}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium border border-[var(--glass-border)] text-[var(--text)] hover:border-[var(--accent)] hover:bg-[var(--msg-user)] transition-all cursor-pointer"
            >
              <svg viewBox="0 0 24 24" width="18" height="18"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
              Continue with Google
            </button>
          </div>

          <div className="mt-4 text-center">
            <button
              onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setLocalError(null); }}
              className="text-xs text-[var(--accent)] hover:underline cursor-pointer"
            >
              {mode === 'login' ? "Don't have an account? Register" : 'Already have an account? Sign in'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
