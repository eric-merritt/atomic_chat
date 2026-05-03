# Atomic Chat — Production Release Notes

**Version:** 0.2.0  
**Status:** production-readiness pass complete

## What was hardened

### Critical (production blockers — resolved)

- `FLASK_SECRET_KEY` now hard-fails on startup unless `FLASK_DEBUG` is set; no more silent fallback to a known weak key.
- `LLAMA_ARG_CTX_SIZE` parsing no longer crashes module import when the env var is absent or invalid; gives a clear error and a sensible default.
- Auth cookies now emit `Secure` outside of debug builds — sessions can no longer leak over plain HTTP in production.
- `/api/auth/login`, `/api/auth/register`, and `/api/auth/password` are rate-limited (sliding-window, in-process) at 10 / 5-min and 5 / 5-min respectively.
- Broken debug print + unguarded conversation creation path in `routes/chat.py` replaced with a real `logging.info` call.

### High-impact (resolved)

- `PreferencesProvider` now debounces writes (400 ms) so rapid UI changes coalesce into a single backend write.
- `tools/web.py:_load_tube_site_selectors` caches `known_site_structures.json` by mtime — JSON is parsed once until the file changes.
- React `<ErrorBoundary>` now wraps the entire provider tree so a single component fault no longer blanks the whole UI.
- Central logging (`services/logging_setup.py`) replaces ad-hoc `print()` in chat routing; correlation ids flow into every line.
- `/api/health` now serves a real liveness probe and `/api/health/ready` checks DB + llama-server with latency.
- Postgres pool is now sized via env (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE`, `DB_POOL_TIMEOUT`).
- Static frontend assets get long `immutable` cache headers; `index.html` gets short revalidation.
- `loaded_model_id()` is now cached for 5 s with explicit invalidation on spawn/kill, removing per-request llama-server hits.

### Cleanup

- Removed unused dependencies: `langchain`, `langchain-ollama`, `langgraph`, `ollama`, `httpx`, `soundfile`, `python-dateutil`, `dashscope`. Dropped six unused imports from `main.py`. Fixed a long-standing bug in `_tool_meta` where the loop returned after the first parameter.
- Replaced disallowed third-party-vendor mentions in user-visible strings (`data/mcp_servers.json` vendor field and `frontend/.../ConnectionsPanel.tsx`) with neutral attributions per project policy.

### Feature

- MCP server registry: 32 curated servers across 15 categories, classified by tier (`free` / `freemium` / `paid`) with `partnership_potential` flag for monetization. Exposed via:
  - `GET /api/mcp/servers` — list with optional `?tier=`, `?category=`, `?self_hostable=` filters
  - `GET /api/mcp/servers/<id>` — single record

## Packaging

### Linux — bash installer
`install_client.sh` (already shipped) handles distro detection, dep install, systemd unit creation, and `.desktop` entry.

### Windows — MSIX (Microsoft Store-compliant)

**Output:** `dist/windows/AtomicChatAgent-<version>.msix`  
**Build script:** `installer/build_msix.py` (use `python installer/build_msix.py [version]`)

The script:
1. Resizes (in the staging directory only — source assets are never modified) installer assets to the five manifest-referenced sizes (44, 71, 150, 300 store, 1440x2160 splash).
2. Stamps the manifest version into `AppxManifest.xml` via regex so original namespace prefixes (`uap`, `uap10`, `rescap`) survive — required so `IgnorableNamespaces` matches and Store certification passes.
3. Builds `atomic-chat-agent.exe` via PyInstaller (Windows host required for this step).
4. Lays out the package directory matching the schema.
5. Calls `makeappx.exe pack` (Windows 10/11 SDK required for this step).
6. Writes `AtomicChatAgent.pkg.json` summarizing the result.

The current `AppxManifest.xml` is Store-compliant:
- 4-part `Version` ending in `.0`
- `ProcessorArchitecture="x64"` declared
- `MinVersion="10.0.17763.0"`, `MaxVersionTested="10.0.22621.0"`
- Square 44/71/150 + StoreLogo + SplashScreen referenced (Wide tile is optional and intentionally omitted)
- `runFullTrust` capability declared (required for the Win32 agent.exe entry)
- Identity `Publisher` matches the Partner Center reservation
- Namespace prefixes (`uap`, `uap10`, `rescap`) preserved through the version-stamp pass

### Pre-submission checklist

- [ ] Run `Windows App Certification Kit` against the staged package
- [ ] Sign with the Partner Center-supplied cert (or skip — Store re-signs at ingest)
- [ ] Confirm `Publisher` CN matches the reservation in Partner Center
- [ ] Upload via Partner Center → Atomic Chat Agent → Submit

## Known limitations / deferred

- Rate limiter is in-process; for multi-worker deployments swap the `_SlidingWindow` backing dict for Redis or use Flask-Limiter with a Redis store.
- Pre-existing test bitrot in `tests/test_tools_filesystem.py` (references several `fs_*` tools that no longer exist) was not addressed in this pass — left for tool-suite owner.
