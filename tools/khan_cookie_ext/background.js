// background.js — listens for cookie sync requests and returns live cookies.
//
// Messages:
//   {action: "get_cookies", domain: ".khanacademy.org"}
//     → returns all cookies for that domain using browser.cookies.getAll()
//   {action: "get_all_domains"}
//     → returns all cookies grouped by domain

browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "get_cookies") {
    const domain = message.domain || "";
    if (!domain) {
      sendResponse({error: "domain is required"});
      return;
    }

    const cleanDomain = domain.replace(/^\./, "");

    browser.cookies.getAll({domain: cleanDomain}).then(cookies => {
      const out = cookies.map(c => ({
        name: c.name,
        value: c.value,
        domain: c.domain,
        hostOnly: c.hostOnly,
        path: c.path,
        secure: c.secure,
        httpOnly: c.httpOnly,
        sameSite: c.sameSite || "no_restriction",
        session: c.session,
        expirationDate: c.expirationDate || null,
      }));
      sendResponse({cookies: out, count: out.length});
    }).catch(err => {
      sendResponse({error: String(err)});
    });

    return true;
  }

  if (message.action === "get_all_domains") {
    browser.cookies.getAll({}).then(cookies => {
      const grouped = {};
      for (const c of cookies) {
        const d = c.domain;
        if (!grouped[d]) grouped[d] = 0;
        grouped[d]++;
      }
      sendResponse({domains: grouped, total: cookies.length});
    }).catch(err => {
      sendResponse({error: String(err)});
    });
    return true;
  }
});
