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
    if (!resp.ok) return { error: `Session check failed (HTTP ${resp.status})` };
    return await resp.json();
  } catch {
    return { error: 'Cannot reach server — check your network or that the backend is running on port 5000' };
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
    if (!resp.ok) return { error: data.error || `Login failed (HTTP ${resp.status})` };
    return data;
  } catch {
    return { error: 'Cannot reach server — check your network or that the backend is running on port 5000' };
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
    if (!resp.ok) return { error: data.error || `Registration failed (HTTP ${resp.status})` };
    return data;
  } catch {
    return { error: 'Cannot reach server — check your network or that the backend is running on port 5000' };
  }
}

export async function logout(): Promise<void> {
  await fetch('/api/auth/logout', { ...OPTS, method: 'POST' });
}

export function oauthRedirect(provider: 'github' | 'google') {
  window.location.href = `/api/auth/oauth/${provider}`;
}
