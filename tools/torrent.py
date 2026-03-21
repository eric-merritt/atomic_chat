"""Torrent tools: search via qBittorrent Web API."""

import os
import time
import json
import urllib.request
import urllib.parse
import http.cookiejar

from langchain.tools import tool

# ── qBittorrent connection ────────────────────────────────────────────────────

QB_URL = os.environ.get("QB_URL", "http://localhost:9441")
QB_USER = os.environ.get("QB_USER", "admin")
QB_PASS = os.environ.get("QBITTORRENT_PASSWORD")

# Cache last search results so torrent_download can reference by index
_last_search_results: list[dict] = []

# Session cookie jar — persists SID across requests
_cookie_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cookie_jar))
_authenticated = False


def _qb_login():
    """Authenticate with qBittorrent and store the session cookie."""
    global _authenticated
    url = f"{QB_URL}/api/v2/auth/login"
    body = urllib.parse.urlencode({"username": QB_USER, "password": QB_PASS}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with _opener.open(req, timeout=10) as resp:
        result = resp.read().decode()
        if "Ok" in result:
            _authenticated = True
        else:
            raise ConnectionError(f"qBittorrent auth failed: {result}")


def _qb_request(path: str, params: dict | None = None, method: str = "GET") -> dict | list | str:
    """Make an authenticated request to the qBittorrent API."""
    global _authenticated
    if not _authenticated:
        _qb_login()

    url = f"{QB_URL}{path}"
    body = None
    if method == "POST" and params:
        body = urllib.parse.urlencode(params).encode()
    elif method == "GET" and params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, data=body, method=method)
    if method == "POST":
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with _opener.open(req, timeout=30) as resp:
            raw = resp.read().decode()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw
    except urllib.error.HTTPError as e:
        if e.code == 403:
            # Session expired — re-auth and retry once
            _authenticated = False
            _qb_login()
            with _opener.open(req, timeout=30) as resp:
                raw = resp.read().decode()
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return raw
        raise


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def torrent_search(query: str, plugins: str = "all", category: str = "all", max_results: int = 20) -> str:
    """Search for torrents using qBittorrent's search plugins.

    Starts a search, waits for completion, and returns results sorted by seeders.

    Args:
        query: Search terms.
        plugins: Plugin to use — "all" for all enabled, or a specific plugin name.
        category: Category filter — "all", "movies", "tv", "music", "games", "software", etc.
        max_results: Maximum number of results to return.
    """
    try:
        resp = _qb_request("/api/v2/search/start", {
            "pattern": query,
            "plugins": plugins,
            "category": category,
        }, method="POST")
    except Exception as e:
        return f"ERROR: Could not start search: {e}"

    search_id = resp.get("id") if isinstance(resp, dict) else None
    if search_id is None:
        return f"ERROR: Unexpected response from search/start: {resp}"

    # Poll for completion (max 60s)
    for _ in range(60):
        time.sleep(1)
        try:
            status = _qb_request("/api/v2/search/status", {"id": search_id})
        except Exception:
            continue
        if isinstance(status, list) and status:
            st = status[0]
        elif isinstance(status, dict):
            st = status
        else:
            continue
        if st.get("status") == "Stopped":
            break
        total = st.get("total", 0)
        if total >= max_results * 2:
            # Enough results, stop early
            try:
                _qb_request("/api/v2/search/stop", {"id": search_id}, method="POST")
            except Exception:
                pass
            break

    # Fetch results
    try:
        data = _qb_request("/api/v2/search/results", {
            "id": search_id,
            "limit": max_results * 3,
            "offset": 0,
        })
    except Exception as e:
        return f"ERROR: Could not fetch results: {e}"

    # Clean up
    try:
        _qb_request("/api/v2/search/delete", {"id": search_id}, method="POST")
    except Exception:
        pass

    results = data.get("results", []) if isinstance(data, dict) else []
    if not results:
        return f"No results found for: {query}"

    # Sort by seeders descending
    results.sort(key=lambda r: r.get("nbSeeders", 0), reverse=True)
    results = results[:max_results]

    # Cache for torrent_download
    _last_search_results.clear()
    _last_search_results.extend(results)

    lines = [f"Found {len(results)} results for '{query}':\n"]
    for i, r in enumerate(results, 1):
        size_bytes = r.get("fileSize", 0)
        size_mb = size_bytes / (1024 * 1024)
        size_str = f"{size_mb:.0f} MB" if size_mb < 1024 else f"{size_mb / 1024:.2f} GB"
        seeders = r.get("nbSeeders", 0)
        leechers = r.get("nbLeechers", 0)
        name = r.get("fileName", "Unknown")
        site = r.get("siteUrl", "?")

        # Seed ratio hint for the model
        ratio = f"{seeders / leechers:.1f}" if leechers else "inf"

        lines.append(
            f"{i}. {name}\n"
            f"   Size: {size_str}  Seeds: {seeders}  Leech: {leechers}  "
            f"S/L: {ratio}  Site: {site}"
        )
    lines.append(
        "\nAnalyze filenames for language, quality, and legitimacy before recommending. "
        "Use torrent_download with the result number(s) to start downloading."
    )
    return "\n".join(lines)


@tool
def torrent_list_plugins() -> str:
    """List all installed qBittorrent search plugins and their status."""
    try:
        plugins = _qb_request("/api/v2/search/plugins")
    except Exception as e:
        return f"ERROR: Could not list plugins: {e}"

    if not isinstance(plugins, list) or not plugins:
        return "No search plugins installed."

    lines = ["Installed search plugins:\n"]
    for p in plugins:
        status = "enabled" if p.get("enabled") else "disabled"
        lines.append(
            f"  - {p.get('fullName', p.get('name', '?'))} [{status}]\n"
            f"    Categories: {', '.join(p.get('supportedCategories', []))}\n"
            f"    URL: {p.get('url', 'N/A')}"
        )
    return "\n".join(lines)


@tool
def torrent_enable_plugin(names: str, enable: bool = True) -> str:
    """Enable or disable qBittorrent search plugins.

    Args:
        names: Plugin names separated by | (e.g. "piratebay|limetorrents").
        enable: True to enable, False to disable.
    """
    try:
        _qb_request("/api/v2/search/enablePlugin", {
            "names": names,
            "enable": str(enable).lower(),
        }, method="POST")
    except Exception as e:
        return f"ERROR: Could not update plugins: {e}"

    action = "Enabled" if enable else "Disabled"
    return f"{action}: {names}"


@tool
def torrent_add(urls: str, category: str = "", paused: bool = False) -> str:
    """Add torrents to qBittorrent for download.

    Args:
        urls: Magnet links or torrent URLs, one per line or separated by |.
        category: Optional category to assign (e.g. "movies", "linux-isos").
        paused: If True, add in paused state.
    """
    url_list = [u.strip() for u in urls.replace("|", "\n").split("\n") if u.strip()]
    if not url_list:
        return "ERROR: No URLs provided."

    params = {
        "urls": "\n".join(url_list),
    }
    if category:
        params["category"] = category
    if paused:
        params["paused"] = "true"

    try:
        resp = _qb_request("/api/v2/torrents/add", params, method="POST")
    except Exception as e:
        return f"ERROR: Could not add torrents: {e}"

    if isinstance(resp, str) and "ok" in resp.lower():
        return f"Added {len(url_list)} torrent(s)."
    return f"Response: {resp}"


@tool
def torrent_list_active(limit: int = 10) -> str:
    """List active/downloading torrents in qBittorrent.

    Args:
        limit: Maximum number of torrents to show.
    """
    try:
        torrents = _qb_request("/api/v2/torrents/info", {"filter": "all", "limit": str(limit)})
    except Exception as e:
        return f"ERROR: Could not list torrents: {e}"

    if not isinstance(torrents, list) or not torrents:
        return "No active torrents."

    lines = [f"Torrents ({len(torrents)}):\n"]
    for t in torrents:
        size_gb = t.get("size", 0) / (1024 ** 3)
        progress = t.get("progress", 0) * 100
        state = t.get("state", "?")
        dl = t.get("dlspeed", 0) / (1024 * 1024)
        lines.append(
            f"  - {t.get('name', '?')}\n"
            f"    State: {state}  Progress: {progress:.1f}%  "
            f"Size: {size_gb:.1f} GB  DL: {dl:.1f} MB/s"
        )
    return "\n".join(lines)


@tool
def torrent_download(picks: str, category: str = "", paused: bool = False) -> str:
    """Download torrents from the most recent search results by their result numbers.

    Call torrent_search first, then use this to download specific results.

    Args:
        picks: Result numbers to download, e.g. "1" or "1,3,5" or "1-3".
        category: Optional category to assign (e.g. "movies", "linux-isos").
        paused: If True, add in paused state.
    """
    if not _last_search_results:
        return "ERROR: No search results cached. Run torrent_search first."

    # Parse picks like "1", "1,3,5", "1-3", "1,3-5"
    indices = set()
    for part in picks.split(","):
        part = part.strip()
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                for n in range(int(a), int(b) + 1):
                    indices.add(n)
            except ValueError:
                return f"ERROR: Invalid range '{part}'. Use e.g. '1-3'."
        else:
            try:
                indices.add(int(part))
            except ValueError:
                return f"ERROR: Invalid number '{part}'."

    urls = []
    names = []
    for idx in sorted(indices):
        if idx < 1 or idx > len(_last_search_results):
            return f"ERROR: Result #{idx} out of range (1-{len(_last_search_results)})."
        r = _last_search_results[idx - 1]
        url = r.get("fileUrl", "")
        if not url:
            return f"ERROR: Result #{idx} has no download URL."
        urls.append(url)
        names.append(r.get("fileName", f"#{idx}"))

    params = {"urls": "\n".join(urls)}
    if category:
        params["category"] = category
    if paused:
        params["paused"] = "true"

    try:
        resp = _qb_request("/api/v2/torrents/add", params, method="POST")
    except Exception as e:
        return f"ERROR: Could not add torrents: {e}"

    if isinstance(resp, str) and "ok" in resp.lower():
        added = "\n".join(f"  - {n}" for n in names)
        return f"Added {len(urls)} torrent(s) to downloads:\n{added}"
    return f"Response: {resp}"


TORRENT_TOOLS = [torrent_search, torrent_download, torrent_list_plugins, torrent_enable_plugin, torrent_add, torrent_list_active]
