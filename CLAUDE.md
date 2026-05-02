ATOMIC CHAT // BRIEF
ARCH: Flask (BE) + React/TS (FE) + qwen-agent + Ollama. NDJSON streaming. Atomic UI. Tailwind v4.
CORE RULE: ALL @register_tool items are ALWAYS ACTIVE. Zero curation/selection.
RUN: ./start.sh | BE: uv run python main.py (:5000) | FE: cd frontend && npm run dev (:5173) | DB: uv run alembic upgrade head | TEST: pytest / npx vitest run
BE CORE: main.py (chat loop) | config.py (LLM/Ollama) | tools/ (impls) | auth/ (DB/models/routes) | routes/ (API) | pipeline/ (tool groups)
FE CORE: frontend/CLAUDE.md = master spec | App.tsx = provider/router hub | Atomic hierarchy (atoms→pages)
TASK → FILES:
• Chat/Stream → main.py, context.py, workflow_groups.py, ChatProvider.tsx, useStream.ts
• Accounting → tools/accounting.py, auth/accounting_models.py, routes/accounting.py
• Auth → auth/ (models/routes/middleware), AuthProvider.tsx
• Tools → tools/, __init__.py, ToolProvider.tsx
• Convos → auth/conversations.py, routes/conversations.py
• DB/Migrate → auth/db.py + models, alembic/
• UI → frontend/src/components/, frontend/CLAUDE.md
