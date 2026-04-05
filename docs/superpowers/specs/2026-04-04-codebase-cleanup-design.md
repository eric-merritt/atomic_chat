# Codebase Cleanup Design Spec

**Date:** 2026-04-04
**Goal:** Clean root directory, refactor tools to Playwright MCP style, kill dead code, consolidate pipeline.

---

## 1. Root Directory Cleanup

### Keep in root (belongs here)
- `main.py` — Flask app entrypoint
- `tools_server.py` — outbound MCP tool server
- `config.py` — env-driven constants
- `context.py` — message format conversion
- `pyproject.toml`, `uv.lock` — project config
- `start.sh` — launch script
- `.env`, `.gitignore`, `.nvmrc`, `.python-version` — dotfiles
- `CLAUDE.md` — project instructions

### Move into packages
| File(s) | Destination | Notes |
|---------|-------------|-------|
| `change_hats.py` | `pipeline/gate.py` | Rename: it classifies + plans |
| `task_extractor.py` | `pipeline/task_extractor.py` | |
| `tool_curator.py` | `pipeline/tool_curator.py` | |
| `workflow_groups.py` | `pipeline/workflow_groups.py` | |
| `credentials.py` | `auth/credentials.py` | |
| `client_agent.py`, `client_bridge.py` | `atomic_client/` | Stubs for future replacement |

### Delete (dead code / artifacts)
| File | Reason |
|------|--------|
| `chained_assistant.py` | Dead iteration, replaced by qwen-agent |
| `chain_planner.py` | Dead iteration |
| `Toolchain.py` | Dead iteration |
| `toolchains.py` | Dead iteration |
| `checkpoints.db`, `.db-shm`, `.db-wal` | LangChain checkpoint leftovers |
| `firebase-debug.log` | 310KB debug log |
| `main.css` | Old pre-React CSS |
| `get-agent.sh`, `get-agent.ps1` | Old installer scripts |
| `install_client.sh`, `install_client.ps1` | Old installer scripts |
| `PROMPT.md` | Superseded by CLAUDE.md |
| `TIMELINE.md` | Historical, not operational |
| `TOOLS.md` | Will be auto-generated from tool registry |
| `README.md` | Move to `docs/` if wanted, delete from root |
| `claude_resume.txt` | Personal file |
| `.zshrc` | Personal file |
| `code_db/` | Dead link list binary |
| `static/` | Old pre-React static assets |
| `migrations/` | Superseded by `alembic/` |
| `nginx/` | Deploy config — move to `docs/deploy/` or delete |

### Training data
- Keep `training_data/archive/2026-03-27-*` (pre-breakage, good data)
- `head -100` each `.jsonl` in `training_data/logs/` and resave (trim recent broken runs)
- Delete `training_data/round1_prompts.md`, `training_data/run_prompts.py` if dead

### Target root after cleanup
```
.
├── main.py
├── tools_server.py
├── config.py
├── context.py
├── pyproject.toml
├── uv.lock
├── start.sh
├── CLAUDE.md
├── .env / .gitignore / .nvmrc / .python-version
├── alembic/
├── auth/
├── atomic_client/        (stubs)
├── docs/
├── frontend/
├── pipeline/             (gate, extractor, curator, workflow_groups)
├── routes/
├── tests/
├── tools/
└── training_data/
```

---

## 2. Tool Refactor — Playwright MCP Style

### Design principles (from Playwright MCP reference)
1. **One tool = one action.** Parameters handle variations, not separate tools.
2. **No dispatchers.** No tool exists solely to route to other tools.
3. **No aliases.** If a function just calls another function with the same args, delete it.
4. **Flat params.** Simple types, short descriptions, no nesting.
5. **Short descriptions.** One line, starts with a verb.
6. **Lightweight.** No over-validation. No redundant checks. Guard at boundaries only.

### Specific changes

#### `tools/accounting.py` (1805 → ~1200 lines)
- **Delete 10 alias functions:** `_debit_asset`, `_credit_asset`, `_debit_liability`, `_credit_liability`, `_debit_equity`, `_credit_equity`, `_debit_revenue`, `_credit_revenue`, `_debit_expense`, `_credit_expense`. They all just call `_debit_account` or `_credit_account`.
- **Delete `_PRIMITIVE_DISPATCH` table.** Replace with direct calls: `side == "debit"` → `_debit_account()`, else `_credit_account()`.
- **Delete `_journalize_fifo_transaction_impl` and `_journalize_lifo_transaction_impl`.** They're one-line wrappers. Call `_journalize_cost_layer_sale` directly from the tool's `call()`.
- **Merge `fa_tx_fifo` + `fa_tx_lifo` → `fa_tx_sale`** with a `method: "fifo" | "lifo"` param.
- **Keep `fa_stmt` as-is** — it already follows the "one tool, type param picks behavior" pattern.
- **Extract DB session boilerplate** into a decorator or context manager. Every tool repeats: `db = _get_db(); try: ... db.commit() except: db.rollback() finally: db.close()`.
- **Kill `_foo_impl` indirection** where the impl function is only called from one place. Inline it into the tool's `call()`, or if shared, keep as a private function but don't wrap it in a second layer.

#### `tools/ecommerce.py` (1270 → ~900 lines)
- **Delete `ec_search` dispatcher** and `_EC_SEARCH_HANDLERS` table. Register `EbaySearchTool`, `AmazonSearchTool`, `CraigslistSearchTool` etc. directly.
- **Merge `EbaySearchTool` + `EbaySoldSearchTool` + `EbayDeepScanTool` → `ebay_search`** with `sold: bool` and `pages: int` params. One URL builder, not three copies.
- **Merge `CraigslistSearchTool` + `CraigslistMultiSearchTool` → `cl_search`** with `city` (single) vs `scope` (multi) param.
- **Delete `CrossPlatformSearchTool`** — if someone wants to search all platforms, they call each tool. The LLM can chain them.
- **Delete `DealFinderTool`** — this is analysis logic that belongs in the LLM's reasoning, not a tool. Or keep as a simple standalone if it's actually used.
- **Extract shared eBay URL builder** — one function builds the URL from query/sort/condition/price params.
- **Extract `_validate_query()`** — replaces the `if not query or not query.strip()` copy-pasted in every tool.

#### `tools/onlyfans.py` (290 → ~220 lines)
- **Merge `of_save_img` + `of_save_vid` → `of_save_media`** — identical implementation (requests.get + write bytes).

#### `tools/web.py` (553 → ~450 lines)
- **Fix `www_cookies`** — `call()` references undefined `dot_domain`, broken `parameters` dict (uses Python `type` and `object` instead of JSON schema strings).
- **Extract `_validate_url()`** — replaces `if not url or not url.startswith(("http://", "https://"))` in 5+ places.
- **Flatten negation patterns** — `if not X: return error` then proceed, instead of `if not X: ... else: ...`.

#### `tools/torrent.py` — no structural changes needed, already clean.
#### `tools/filesystem.py` — no structural changes needed, already clean.
#### `tools/codesearch.py` — no structural changes needed, already clean.

### Naming convention (all tools)
Follow `domain_action` pattern: `ebay_search`, `cl_search`, `www_fetch`, `fa_tx_new`, `bt_search`, `fs_read`, etc. Existing `fa_*`, `fs_*`, `cs_*`, `bt_*`, `www_*` prefixes are already good.

---

## 3. Pipeline Consolidation

### Current state (broken)
Four overlapping systems doing task extraction and tool routing:
1. `change_hats.py` — Gate (classify) + Plan (build task chain with subtask→tool mappings)
2. `task_extractor.py` — Separate 1.7B LLM that also extracts tasks
3. `tool_curator.py` — Separate 1.7B LLM that also maps tasks→tools→groups
4. `main.py` lines 430-534 — Inline code that ALSO maps subtask actions→groups, plus recommendation pause/resume

**Result:** Tools never reach the agent. The flow is too fragmented to debug.

### Target state
One package: `pipeline/`. One flow:

```
User message
  → pipeline.gate.classify(msg) → "conversational" | "tool_required" | "mixed"
  → if tool_required/mixed:
      pipeline.task_extractor.extract(msg, conv_id) → new tasks in DB
      pipeline.tool_curator.curate(conv_id, user_tools) → {groups_needed, task_plan}
      → emit recommendation if missing groups
      → build function_list from approved groups
  → main.py passes function_list to Assistant
```

- `change_hats.py` → `pipeline/gate.py` (Gate call only — classification)
- Plan call from `change_hats.py` is deleted — the curator already does task→tool mapping
- `main.py` inline tool routing (lines 466-534) moves into `pipeline/tool_curator.py`
- Single source of truth for "which tools does the agent get"

### `pipeline/__init__.py` — public API
```python
def process_message(user_msg, conversation_id, user_tool_names, db):
    """Classify, extract tasks, curate tools. Returns function_list."""
```

`main.py` calls this one function. Done.

---

## 4. System Prompt Fix

The current `_SYSTEM_BASE` in `main.py` frames the agent as a tool-calling robot that tolerates conversation. Combined with the gate stripping all tools on "conversational" messages, the model has nothing to do and gets dismissive ("I'm just here to call tools").

**Fix:** Rewrite the system prompt so the agent is conversational first, tool-capable second. The personality should be friendly and engaged regardless of whether tools are needed. Tools are capabilities, not identity.

Key changes:
- Remove "If a message requires tools you must call them. If it does not, be conversational." — this creates a binary identity crisis.
- Remove "ACT FIRST, explain later. Do NOT explain to the user how you're going to perform a task." — this makes the agent antisocial.
- Remove "The ONLY time it is acceptable to respond with a tool's content..." — too restrictive.
- Keep the practical rules: don't invent tool names, don't guess params, use `get_params` first.
- Add: "You are a helpful assistant. You can use tools when needed, but you're also great at conversation, explanation, and reasoning."

---

## 5. Control Flow Style

Throughout all files:
- **Early return over else.** `if bad: return error` then proceed at top level.
- **No `if not X: ... else: ...`** when `if X: (early return)` reads cleaner.
- **No double-negation.** `if not query or not query.strip()` → `if not query.strip()` (empty string is falsy).

---

## 5. Out of Scope

- Frontend changes (separate effort)
- Database schema changes
- New features
- The actual bug fix for tools not reaching the agent (will fall out of pipeline consolidation, but debugging it is not the goal here)
