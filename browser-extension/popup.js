const fmt = (ts) => ts ? new Date(ts).toLocaleTimeString() : '—';

const render = ({ cookiePayload, lastSync, blocked }) => {
  const domains = (cookiePayload || []).length;
  const total = (cookiePayload || []).reduce((sum, d) => sum + d.cookies.length, 0);
  document.getElementById('domains').textContent = domains;
  document.getElementById('cookies').textContent = total;
  document.getElementById('blocked').textContent = blocked ?? '—';
  document.getElementById('lastSync').textContent = fmt(lastSync);
};

chrome.storage.local.get(['cookiePayload', 'lastSync', 'blocked'], render);

document.getElementById('syncBtn').addEventListener('click', async () => {
  document.getElementById('status').textContent = 'syncing…';
  await chrome.runtime.sendMessage({ type: 'FORCE_SYNC' });
  setTimeout(() => {
    chrome.storage.local.get(['cookiePayload', 'lastSync', 'blocked'], (data) => {
      render(data);
      document.getElementById('status').textContent = 'done';
    });
  }, 2000);
});
