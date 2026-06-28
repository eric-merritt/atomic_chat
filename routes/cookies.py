"""Cookie sync endpoint — receives cookies from the frontend's CookieProvider
(which reads window._atomicChatCookieStore set by the browser extension)
and stores them where agent tools can access them."""

import logging
from flask import Blueprint, jsonify, request
from flask_login import login_required
from tools.web import sync_cookies_from_frontend

log = logging.getLogger(__name__)

cookies_bp = Blueprint("cookies", __name__, url_prefix="/api/cookies")


@cookies_bp.route("/sync", methods=["POST"])
@login_required
def sync_cookies():
  """Receive cookie store from frontend and persist for agent tools.

  Body: { cookies: [{ domain: ".example.com", cookies: [{name, value, ...}, ...] }] }
  """
  data = request.get_json(silent=True)
  if not data or "cookies" not in data:
    return jsonify({"error": "Missing 'cookies' array in body"}), 400

  cookie_entries = data["cookies"]
  if not isinstance(cookie_entries, list):
    return jsonify({"error": "'cookies' must be an array"}), 400

  synced = 0
  for entry in cookie_entries:
    domain = entry.get("domain", "").strip()
    cookies = entry.get("cookies", [])
    if not domain or not isinstance(cookies, list):
      continue
    for c in cookies:
      name = c.get("name", "").strip()
      value = c.get("value", "")
      if name:
        sync_cookies_from_frontend(domain, name, value, c)
        synced += 1

  log.info("Frontend cookie sync: %d cookies from %d domains", synced, len(cookie_entries))
  return jsonify({"synced": synced, "domains": len(cookie_entries)})
