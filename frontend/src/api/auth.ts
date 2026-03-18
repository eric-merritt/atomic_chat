import type { User } from '../atoms/user';

const HEADERS = { 'Content-Type': 'application/json' };
const OPTS: RequestInit = { credentials: 'include' };

interface AuthResponse {
  user?: User;
  error?: string;
}

export async function fetchMe(): Promise<AuthResponse> {
  try {
    const resp = await fetch('/api/auth/me', OPTS);
    if (!resp.ok) return { error: `${resp.status}` };
    return await resp.json();
  } catch {
    return { error: 'Network error' };
  }
}

export async function login(username: string, password: string): Promise<AuthResponse> {
  try {
    const resp = await fetch('/api/auth/login', {
      ...OPTS,
      method: 'POST',
      headers: HEADERS,
      body: JSON.stringify({ username, password }),
    });
    const data = await resp.json();
    if (!resp.ok) return { error: data.error || 'Login failed' };
    return data;
  } catch {
    return { error: 'Network error' };
  }
}

export async function register(
  username: string, email: string, password: string,
): Promise<AuthResponse> {
  try {
    const resp = await fetch('/api/auth/register', {
      ...OPTS,
      method: 'POST',
      headers: HEADERS,
      body: JSON.stringify({ username, email: email || undefined, password }),
    });
    const data = await resp.json();
    if (!resp.ok) return { error: data.error || 'Registration failed' };
    return data;
  } catch {
    return { error: 'Network error' };
  }
}

export async function logout(): Promise<void> {
  await fetch('/api/auth/logout', { ...OPTS, method: 'POST' });
}

export function oauthRedirect(provider: 'github' | 'google') {
  window.location.href = `/api/auth/oauth/${provider}`;
}
