const BACKEND_URL = 'http://localhost:8297/api/cookies/sync';
const ATOMIC_CHAT_TAB_URL = 'http://localhost:6612/*';
const BATCH_DELAY_MS = 1500;

const OAUTH_NAMES = new Set([
  'state', 'nonce', 'pkce_state', 'code_verifier', 'pkce_code_verifier',
  'oauth_token', 'oauth_token_secret', 'oauth_verifier', 'oauth_state',
  'auth_state', 'oidc_nonce', 'oauth_nonce', 'openid_state', 'login_hint',
]);

const OAUTH_PATH_SEGMENTS = ['/oauth', '/authorize', '/callback', '/sso', '/oidc'];

const isOAuthCookie = (cookie) => {
  if (OAUTH_NAMES.has(cookie.name.toLowerCase())) return true;
  if (OAUTH_PATH_SEGMENTS.some(seg => (cookie.path || '').toLowerCase().includes(seg))) return true;
  if (cookie.expirationDate) {
    const ttl = cookie.expirationDate - Date.now() / 1000;
    if (ttl > 0 && ttl < 300) return true;
  }
  return false;
};

const groupByDomain = (cookies) => {
  const byDomain = {};
  for (const cookie of cookies) {
    if (isOAuthCookie(cookie)) continue;
    const domain = cookie.domain.startsWith('.') ? cookie.domain : '.' + cookie.domain;
    if (!byDomain[domain]) byDomain[domain] = [];
    byDomain[domain].push({
      name: cookie.name,
      value: cookie.value,
      path: cookie.path,
      secure: cookie.secure,
      httpOnly: cookie.httpOnly,
      sameSite: cookie.sameSite,
      expirationDate: cookie.expirationDate,
    });
  }
  return Object.entries(byDomain).map(([domain, cookies]) => ({ domain, cookies }));
};

const collectAndStore = async () => {
  const allCookies = await chrome.cookies.getAll({});
  const filtered = groupByDomain(allCookies);
  const blocked = allCookies.length - filtered.reduce((sum, d) => sum + d.cookies.length, 0);
  await chrome.storage.local.set({ cookiePayload: filtered, lastSync: Date.now(), blocked });
  return filtered;
};

const pushToAtomicChat = async (payload) => {
  const tabs = await chrome.tabs.query({ url: ATOMIC_CHAT_TAB_URL });
  for (const tab of tabs) {
    chrome.tabs.sendMessage(tab.id, { type: 'COOKIE_SYNC', cookies: payload }).catch(() => {});
  }
};

const syncAll = async () => {
  const payload = await collectAndStore();
  await pushToAtomicChat(payload);
};

let debounceTimer = null;
const scheduledSync = () => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(syncAll, BATCH_DELAY_MS);
};

chrome.cookies.onChanged.addListener(({ removed }) => {
  if (!removed) scheduledSync();
});

// Push stored cookies when atomic_chat tab loads
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== 'complete') return;
  if (!tab.url?.startsWith('http://localhost:6612')) return;
  const { cookiePayload } = await chrome.storage.local.get('cookiePayload');
  if (cookiePayload) {
    chrome.tabs.sendMessage(tabId, { type: 'COOKIE_SYNC', cookies: cookiePayload }).catch(() => {});
  }
});

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'FORCE_SYNC') syncAll();
});

chrome.runtime.onStartup.addListener(syncAll);
chrome.runtime.onInstalled.addListener(syncAll);
