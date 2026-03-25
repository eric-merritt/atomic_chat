"""Torrent tools: search via qBittorrent Web API."""

import os
import time
import json
import urllib.request
import urllib.parse
import http.cookiejar

import json5
from qwen_agent.tools.base import BaseTool, register_tool
from tools._output import tool_result, retry

# ── qBittorrent connection ────────────────────────────────────────────────────

QB_URL = os.environ.get("QB_URL", "http://localhost:9441")
QB_USER = os.environ.get("QB_USER", "admin")
QB_PASS = os.environ.get("QBITTORRENT_PASSWORD")

# Session cookie jar — persists SID across requests (single-user CLI only)
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

@register_tool('torrent_search')
class TorrentSearchTool(BaseTool):
    description = "Search for torrents using qBittorrent's search plugins."
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search terms. Must be non-empty.'},
            'plugins': {'type': 'string', 'description': 'Plugin to use. "all" for all enabled, or a specific plugin name.'},
            'category': {'type': 'string', 'description': 'Category filter. "all", "movies", "tv", "music", "games", "software".'},
            'max_results': {'type': 'integer', 'description': 'Maximum number of results to return. Range: 1-100.'},
        },
        'required': ['query'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        query = p['query']
        plugins = p.get('plugins', 'all')
        category = p.get('category', 'all')
        max_results = p.get('max_results', 20)

        if not query or not query.strip():
            return tool_result(error="query must be a non-empty string")

        try:
            resp = _qb_request("/api/v2/search/start", {
                "pattern": query,
                "plugins": plugins,
                "category": category,
            }, method="POST")
        except Exception as e:
            return tool_result(error=f"Could not start search: {e}")

        search_id = resp.get("id") if isinstance(resp, dict) else None
        if search_id is None:
            return tool_result(error=f"Unexpected response from search/start: {resp}")

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
            return tool_result(error=f"Could not fetch results: {e}")

        # Clean up
        try:
            _qb_request("/api/v2/search/delete", {"id": search_id}, method="POST")
        except Exception:
            pass

        results = data.get("results", []) if isinstance(data, dict) else []
        if not results:
            return tool_result(data={"query": query, "count": 0, "results": []})

        # Sort by seeders descending
        results.sort(key=lambda r: r.get("nbSeeders", 0), reverse=True)
        results = results[:max_results]

        formatted = []
        for r in results:
            size_bytes = r.get("fileSize", 0)
            size_mb = size_bytes / (1024 * 1024)
            size_str = f"{size_mb:.0f} MB" if size_mb < 1024 else f"{size_mb / 1024:.2f} GB"
            seeders = r.get("nbSeeders", 0)
            leechers = r.get("nbLeechers", 0)
            ratio = f"{seeders / leechers:.1f}" if leechers else "inf"

            formatted.append({
                "name": r.get("fileName", "Unknown"),
                "size": size_str,
                "seeders": seeders,
                "leechers": leechers,
                "ratio": ratio,
                "site": r.get("siteUrl", "?"),
                "download_url": r.get("fileUrl", ""),
            })

        return tool_result(data={"query": query, "count": len(formatted), "results": formatted})


@register_tool('torrent_list_plugins')
class TorrentListPluginsTool(BaseTool):
    description = 'List all installed qBittorrent search plugins and their status.'
    parameters = {'type': 'object', 'properties': {}, 'required': []}

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        try:
            plugins = _qb_request("/api/v2/search/plugins")
        except Exception as e:
            return tool_result(error=f"Could not list plugins: {e}")

        if not isinstance(plugins, list) or not plugins:
            return tool_result(data={"count": 0, "plugins": []})

        formatted = []
        for p in plugins:
            formatted.append({
                "name": p.get("fullName", p.get("name", "?")),
                "enabled": p.get("enabled", False),
                "categories": p.get("supportedCategories", []),
                "url": p.get("url", ""),
            })

        return tool_result(data={"count": len(formatted), "plugins": formatted})


@register_tool('torrent_enable_plugin')
class TorrentEnablePluginTool(BaseTool):
    description = 'Enable or disable qBittorrent search plugins.'
    parameters = {
        'type': 'object',
        'properties': {
            'names': {'type': 'string', 'description': 'Plugin names separated by | (e.g. "piratebay|limetorrents").'},
            'enable': {'type': 'boolean', 'description': 'True to enable, False to disable.'},
        },
        'required': ['names'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        names = p['names']
        enable = p.get('enable', True)

        if not names or not names.strip():
            return tool_result(error="names must be a non-empty string")

        try:
            _qb_request("/api/v2/search/enablePlugin", {
                "names": names,
                "enable": str(enable).lower(),
            }, method="POST")
        except Exception as e:
            return tool_result(error=f"Could not update plugins: {e}")

        action = "enabled" if enable else "disabled"
        return tool_result(data={"names": names, "action": action})


@register_tool('torrent_add')
class TorrentAddTool(BaseTool):
    description = 'Add torrents to qBittorrent for download by magnet link or URL.'
    parameters = {
        'type': 'object',
        'properties': {
            'urls': {'type': 'string', 'description': 'Magnet links or torrent URLs, one per line or separated by |.'},
            'category': {'type': 'string', 'description': 'Optional category to assign (e.g. "movies", "linux-isos").'},
            'paused': {'type': 'boolean', 'description': 'If True, add in paused state instead of starting immediately.'},
        },
        'required': ['urls'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        urls = p['urls']
        category = p.get('category', '')
        paused = p.get('paused', False)

        url_list = [u.strip() for u in urls.replace("|", "\n").split("\n") if u.strip()]
        if not url_list:
            return tool_result(error="No URLs provided.")

        req_params = {"urls": "\n".join(url_list)}
        if category:
            req_params["category"] = category
        if paused:
            req_params["paused"] = "true"

        try:
            resp = _qb_request("/api/v2/torrents/add", req_params, method="POST")
        except Exception as e:
            return tool_result(error=f"Could not add torrents: {e}")

        if isinstance(resp, str) and "ok" in resp.lower():
            return tool_result(data={"added": len(url_list), "urls": url_list})
        return tool_result(data={"added": len(url_list), "urls": url_list, "response": str(resp)})


@register_tool('torrent_list_active')
class TorrentListActiveTool(BaseTool):
    description = 'List active/downloading torrents in qBittorrent.'
    parameters = {
        'type': 'object',
        'properties': {
            'limit': {'type': 'integer', 'description': 'Maximum number of torrents to show. Range: 1-100.'},
        },
        'required': [],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        limit = p.get('limit', 10)

        try:
            torrents = _qb_request("/api/v2/torrents/info", {"filter": "all", "limit": str(limit)})
        except Exception as e:
            return tool_result(error=f"Could not list torrents: {e}")

        if not isinstance(torrents, list) or not torrents:
            return tool_result(data={"count": 0, "torrents": []})

        formatted = []
        for t in torrents:
            size_gb = t.get("size", 0) / (1024 ** 3)
            progress = t.get("progress", 0) * 100
            dl_speed = t.get("dlspeed", 0) / (1024 * 1024)
            formatted.append({
                "name": t.get("name", "?"),
                "state": t.get("state", "?"),
                "progress": round(progress, 1),
                "size_gb": round(size_gb, 1),
                "dl_speed_mbps": round(dl_speed, 1),
            })

        return tool_result(data={"count": len(formatted), "torrents": formatted})


@register_tool('torrent_download')
class TorrentDownloadTool(BaseTool):
    description = 'Download torrents by URL or magnet link (alias for torrent_add).'
    parameters = {
        'type': 'object',
        'properties': {
            'urls': {'type': 'string', 'description': 'Magnet links or torrent URLs, one per line or separated by |.'},
            'category': {'type': 'string', 'description': 'Optional category to assign (e.g. "movies", "linux-isos").'},
            'paused': {'type': 'boolean', 'description': 'If true, add in paused state instead of starting immediately.'},
        },
        'required': ['urls'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        return TorrentAddTool().call(params, **kwargs)
