export interface CookieEntry {
  name: string;
  value: string;
  domain: string;
  hostOnly?: boolean;
  path?: string;
  secure?: boolean;
  httpOnly?: boolean;
  sameSite?: string;
  session?: boolean;
  expirationDate?: number | null;
}

export type CookieStore = Record<string, CookieEntry[]> & { _ready?: boolean };

export async function syncCookiesToBackend(cookieStore: CookieStore): Promise<{ synced: number }> {
  const entries: { domain: string; cookies: CookieEntry[] }[] = [];
  for (const [domain, cookies] of Object.entries(cookieStore)) {
    if (domain === '_ready' || !Array.isArray(cookies)) continue;
    if (cookies.length === 0) continue;
    entries.push({ domain, cookies });
  }

  if (entries.length === 0) {
    return { synced: 0 };
  }

  const res = await fetch('/api/cookies/sync', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ cookies: entries }),
  });

  if (!res.ok) {
    throw new Error(`Failed to sync cookies: ${res.status}`);
  }

  const data = await res.json();
  return data;
}
