# Atomic Chat

Local-first AI chat app: Flask + qwen-agent + Ollama backend, React + TypeScript frontend. All registered tools are always available to the agent — no curation or selection required.

## Commands

- **Backend:** `uv run python main.py` (Flask on port 5000)
- **Frontend:** `cd frontend && npm run dev` (Vite on port 5173, proxies to backend)
- **Tests (Python):** `uv run pytest` or `uv run pytest tests/test_foo.py -v`
- **Tests (Frontend):** `cd frontend && npx vitest run`
- **Migrations:** `uv run alembic upgrade head`
- **Start all:** `./start.sh`

## Backend layout

- `main.py` — Flask app, `/api/chat/stream` NDJSON endpoint, qwen-agent `Assistant.run()` loop. All tools passed to every request.
- `config.py` — env-driven constants; `qwen_llm_cfg()` builds qwen-agent LLM dict pointing at Ollama's OpenAI-compatible endpoint
- `context.py` — converts DB message rows to qwen-agent message dicts (role/content/name)
- `tools_server.py` — outbound MCP tool server (exposes our tools to external MCP clients)
- `pipeline/` — `workflow_groups.py` (static registry mapping group names to tool lists + `TOOL_REF` descriptions)
- `auth/` — SQLAlchemy models + DB setup (`db.py`, `models.py`, `conversations.py`, `conversation_tasks.py`, `accounting_models.py`, `credentials.py`, `routes.py`, `middleware.py`, `seed.py`)
- `tools/` — tool implementations as qwen-agent `@register_tool` + `BaseTool` classes (`filesystem.py`, `web.py`, `ecommerce.py`, `onlyfans.py`, `torrent.py`, `mcp.py`, `accounting.py`, `_output.py`)
- `routes/` — Flask blueprints (`conversations.py`, `preferences.py`, `accounting.py`, `tools.py`)
- `atomic_client/` — client stubs (`agent.py`, `bridge.py`) for future replacement

## Frontend layout

See `frontend/CLAUDE.md` for full details. Atomic design: atoms → molecules → organisms → pages. Provider chain in `App.tsx`. NDJSON streaming chat. Tailwind v4 with CSS custom properties.

## Context-specific reading guides

**Working on the chat pipeline:**
- `main.py` (`chat_stream` + `generate` — qwen-agent `Assistant.run()` loop)
- `pipeline/workflow_groups.py` (tool groups + `TOOL_REF` descriptions)
- `context.py` (message format conversion)
- `config.py` (`qwen_llm_cfg`)
- `frontend/src/providers/ChatProvider.tsx` + `frontend/src/hooks/useStream.ts` + `frontend/src/atoms/stream.ts`

**Working on accounting:**
- `tools/accounting.py`
- `auth/accounting_models.py`
- `routes/accounting.py`
- `frontend/src/components/organisms/AccountingDashboard.tsx` (if exists)
- `frontend/src/api/accounting.ts` (if exists)

**Working on auth/users:**
- `auth/models.py` + `auth/routes.py` + `auth/middleware.py`
- `frontend/src/providers/AuthProvider.tsx` + `frontend/src/api/auth.ts`
- `frontend/src/pages/LoginPage.tsx`

**Working on tools:**
- `tools/` directory (each file = one tool domain; all use `@register_tool` + `BaseTool`)
- `tools/__init__.py` (imports all modules to trigger registration; `ALL_TOOLS` built from `TOOL_REGISTRY`)
- `pipeline/workflow_groups.py` (tool → group mapping, `TOOL_REF` descriptions)
- `frontend/src/providers/ToolProvider.tsx` + `frontend/src/hooks/useTools.ts`

**Working on conversations/history:**
- `auth/conversations.py` + `auth/conversation_tasks.py`
- `routes/conversations.py`
- `frontend/src/api/conversations.ts` + `frontend/src/providers/ChatProvider.tsx`

**Working on DB schema/migrations:**
- `auth/db.py` + all models in `auth/`
- `alembic/` + `alembic.ini`

**Working on frontend components:**
- `frontend/CLAUDE.md` (has full architecture)
- `frontend/src/components/` (atomic design hierarchy)
- `frontend/src/App.tsx` (provider wiring + routes)
