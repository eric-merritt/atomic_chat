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

# Pending

- MCP server directory feature (fetchable list, paid vs. free tracking)
- Dead code / unused dependency cleanup
- MSIX packaging for Microsoft Store (partner account ready, existing installer needs recert)
- LLM: llama-server, MODEL_NGL=42 ceiling on 4080 SUPER
