chrome.runtime.onMessage.addListener((message) => {
  if (message.type !== 'COOKIE_SYNC') return;
  fetch('http://localhost:8297/api/cookies/sync', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cookies: message.cookies }),
  }).catch(() => {});
});
