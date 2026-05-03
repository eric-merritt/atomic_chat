ATOMIC CHAT // BRIEF
Architecture: Flask (BE) + React/TS (FE) + qwen-agent + Ollama. NDJSON streaming. Atomic UI. Tailwind v4.
RUN: ./start.sh restart -- Kills orphaned processes/running servers, starts all
Backend CORE: main.py (chat loop) | config.py (LLM/Ollama) | tools/ (impls) | auth/ (DB/models/routes) | routes/ (API) | pipeline/ (tool groups)
Frontend CORE: frontend/CLAUDE.md = master spec | App.tsx = provider/router hub | Atomic hierarchy (atoms→pages)
TASK → FILES:
• Chat/Stream → main.py, context.py, workflow_groups.py, ChatProvider.tsx, useStream.ts
• Accounting → tools/accounting.py, auth/accounting_models.py, routes/accounting.py
• Auth → auth/ (models/routes/middleware), AuthProvider.tsx
• Tools → tools/, __init__.py, ToolProvider.tsx
• Convos → auth/conversations.py, routes/conversations.py
• DB/Migrate → auth/db.py + models, alembic/
• UI → frontend/src/components/, frontend/CLAUDE.md

# CURRENT FOCUS - FINAL PRODUCTION READINESS TO-DOS (CHECKLIST PENDING PLAN OF ACTION)

## CRITICAL (6 items — production blockers)

- Hardcoded fallback secret_key that should hard-fail if unset in prod
- config.py crashes at import if LLAMA_ARG_CTX_SIZE env var is missing
- Auth cookies missing secure=True flag — breaks HTTPS security
- No rate limiting on /login, /register, /password
- Broken f-string debug print + logic gap in routes/chat.py that can crash the chat
- ~~"Anthropic" mention in atomic_client/agent.py (your hard-rule)~~

Recommended HIGH priority fixes also include: API key write-storm debounce, known_site_structures.json file caching, ErrorBoundary mounting, structured logging, real /health check, DB connection pool sizing, HTTP cache headers, and loaded_model_id() caching.

---
The agent has its answers and can begin implementing the plan starting with a simplified demonstration of architecture design elements that could create the most ROI in terms of time/tokens:

1. Remediation scope — approve CRITICAL + the 8 named HIGH items? Anything to add or drop?

   *User Answer: approve CRITICAL + 8 HIGH.

2. Any deferred items to pull forward? (langchain dep cleanup, DB session unification, Dockerfile, etc.)

   *User Answer: Final cleanup of all dead code: dependencies, unused functions, etc. This should have been done already. While we're at it let's add one last feature, fetchable list of MCP servers, deep research to define list. Keep track of paid vs. unpaid (potential deals for selling access)

3. Windows packaging — keep PyInstaller .exe only, or also produce an .msix wrapper?

   *User Answer: msix for sure. Already have a partner account for Microsoft store where my current installer is sure to fail certification and will be waiting on a resub.
