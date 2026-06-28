import { createContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { CookieStore, CookieEntry } from '../api/cookies';
import { syncCookiesToBackend } from '../api/cookies';

interface CookieContextValue {
  /** Full cookie store keyed by domain: { ".example.com": [{name, value, ...}, ...] } */
  cookieStore: CookieStore;
  /** Flat list of all cookies across all domains */
  allCookies: CookieEntry[];
  /** Whether the extension-injected store was detected */
  extensionReady: boolean;
  /** Last sync result (number of domains synced) */
  lastSynced: number | null;
  /** Manually trigger a sync to the backend */
  syncToBackend: () => Promise<void>;
  /** Refresh by dispatching atomicChatRefreshCookies for each domain */
  refreshCookies: () => void;
}

export const CookieContext = createContext<CookieContextValue | null>(null);

declare global {
  interface Window {
    _atomicChatCookieStore?: CookieStore;
  }
}

function flattenCookies(store: CookieStore): CookieEntry[] {
  const result: CookieEntry[] = [];
  for (const [domain, cookies] of Object.entries(store)) {
    if (domain === '_ready' || !Array.isArray(cookies)) continue;
    result.push(...cookies);
  }
  return result;
}

function readCookieStoreFromWindow(): CookieStore | null {
  const store = window._atomicChatCookieStore;
  if (!store || !store._ready) return null;
  return { ...store };
}

export function CookieProvider({ children }: { children: ReactNode }) {
  const [cookieStore, setCookieStore] = useState<CookieStore>({});
  const [extensionReady, setExtensionReady] = useState(false);
  const [lastSynced, setLastSynced] = useState<number | null>(null);

  // Initial read from window._atomicChatCookieStore
  useEffect(() => {
    const store = readCookieStoreFromWindow();
    if (store) {
      setExtensionReady(true);
      setCookieStore(store);
    }

    // Poll briefly on mount — the extension may still be populating
    const timer = setInterval(() => {
      const fresh = readCookieStoreFromWindow();
      if (fresh) {
        setExtensionReady(true);
        setCookieStore(fresh);
        clearInterval(timer);
      }
    }, 500);

    return () => clearInterval(timer);
  }, []);

  // Listen for per-domain updates from the extension's CustomEvent
  useEffect(() => {
    const handler = (evt: Event) => {
      const detail = (evt as CustomEvent).detail as { domain: string; cookies: CookieEntry[] };
      if (detail?.domain && Array.isArray(detail.cookies)) {
        setCookieStore(prev => ({
          ...prev,
          [detail.domain]: detail.cookies,
        }));
      }
    };

    window.addEventListener('atomicChatCookiesUpdated', handler);
    return () => window.removeEventListener('atomicChatCookiesUpdated', handler);
  }, []);

  const syncToBackend = useCallback(async () => {
    const store = readCookieStoreFromWindow();
    if (!store) return;
    try {
      const result = await syncCookiesToBackend(store);
      setLastSynced(result.synced);
    } catch {
      // Silently fail — cookies may not be needed for this session
    }
  }, []);

  // Auto-sync when cookies are detected and backend is reachable
  useEffect(() => {
    if (!extensionReady) return;
    const cookies = flattenCookies(cookieStore);
    if (cookies.length === 0) return;

    // Debounced auto-sync on first detection
    const timer = setTimeout(() => {
      syncToBackend();
    }, 2000);

    return () => clearTimeout(timer);
  }, [extensionReady, cookieStore.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const refreshCookies = useCallback(() => {
    const domains = Object.keys(cookieStore).filter(d => d !== '_ready');
    for (const domain of domains) {
      window.dispatchEvent(new CustomEvent('atomicChatRefreshCookies', {
        detail: { domain },
      }));
    }
  }, [cookieStore]);

  return (
    <CookieContext.Provider value={{
      cookieStore,
      allCookies: flattenCookies(cookieStore),
      extensionReady,
      lastSynced,
      syncToBackend,
      refreshCookies,
    }}>
      {children}
    </CookieContext.Provider>
  );
}
