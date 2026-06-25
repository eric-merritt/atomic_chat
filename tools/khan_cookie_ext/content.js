// content.js — bridges page scripts to extension background.
//
// Injects a <script> tag into the page so window._atomicChatCookieStore
// is visible to any page script. Content scripts run in a sandboxed
// context in Firefox — only injected <script> tags share the page's
// real window object.
//
// Usage from any page script:
//   console.log(window._atomicChatCookieStore);
//   // { ".khanacademy.org": [{name, value, ...}, ...] }
//
// To refresh:
//   window.dispatchEvent(new CustomEvent("atomicChatRefreshCookies", {
//     detail: { domain: ".khanacademy.org" }
//   }));

(function() {
  "use strict";

  // Inject a <script> that creates the store object on the real page window.
  // This script runs in the page's JS context, so page scripts can access it.
  var setupScript = document.createElement("script");
  setupScript.textContent =
    "window._atomicChatCookieStore = window._atomicChatCookieStore || {};" +
    "window._atomicChatCookieStore._ready = true;";
  document.documentElement.appendChild(setupScript);
  setupScript.remove();

  // Helper: inject data into the page's store by injecting a <script> tag
  function injectCookies(domain, cookies) {
    var script = document.createElement("script");
    var data = JSON.stringify(cookies);
    script.textContent =
      "window._atomicChatCookieStore[" + JSON.stringify(domain) + "] = " + data + ";" +
      "window.dispatchEvent(new CustomEvent('atomicChatCookiesUpdated', {" +
        "detail: { domain: " + JSON.stringify(domain) + ", cookies: " + data + " }" +
      "}));";
    document.documentElement.appendChild(script);
    script.remove();
  }

  // Fetch cookies for a domain from background and inject into page store
  function fetchAndStore(domain) {
    browser.runtime.sendMessage(
      { action: "get_cookies", domain: domain },
      function(response) {
        if (response && response.cookies) {
          injectCookies(domain, response.cookies);
        }
      }
    );
  }

  // Populate store for all domains
  function initialPopulate() {
    browser.runtime.sendMessage({ action: "get_all_domains" }, function(response) {
      if (response && response.domains) {
        Object.keys(response.domains).forEach(function(domain) {
          var normalized = domain.startsWith(".") ? domain : "." + domain;
          fetchAndStore(normalized);
        });
      }
    });
  }

  // Initial load
  initialPopulate();

  // Listen for refresh requests from page scripts
  document.addEventListener("atomicChatRefreshCookies", function(evt) {
    var domain = evt.detail && evt.detail.domain;
    if (domain) fetchAndStore(domain);
  });

  // Periodic refresh
  setInterval(initialPopulate, 30000);
})();
