import type { Preferences } from '../atoms/user';

const OPTS: RequestInit = { credentials: 'include' };
const HEADERS = { 'Content-Type': 'application/json' };

export async function getPreferences(): Promise<Preferences> {
  const resp = await fetch('/api/auth/preferences', OPTS);
  const data = await resp.json();
  return data.preferences || {};
}

export async function updatePreferences(prefs: Partial<Preferences>): Promise<Preferences> {
  const resp = await fetch('/api/auth/preferences', {
    ...OPTS, method: 'PATCH', headers: HEADERS,
    body: JSON.stringify(prefs),
  });
  const data = await resp.json();
  return data.preferences;
}

export async function updateProfile(data: { username?: string; email?: string }) {
  const resp = await fetch('/api/auth/profile', {
    ...OPTS, method: 'PATCH', headers: HEADERS,
    body: JSON.stringify(data),
  });
  return resp.json();
}

export async function changePassword(currentPassword: string, newPassword: string) {
  const resp = await fetch('/api/auth/password', {
    ...OPTS, method: 'POST', headers: HEADERS,
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  return resp.json();
}
