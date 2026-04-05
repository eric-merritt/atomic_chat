# Round 1 Scorecard — Abliterated Variants

Test date: 2026-03-28 | 3 runs per prompt per model | 17 prompts

## Overall

| Metric | huihui_ai/qwen2.5-coder-abliterate:14b | huihui_ai/qwen3-abliterated:14b |
| --- | --- | --- |
| Total tool calls | 0 | 171 |
| Total tool results | 0 | 166 |
| **Execution rate** | **N/A (no calls)** | **97%** |
| Avg time/prompt | 7.9s | 39.6s |
| Hallucinated tool names | Every response (tool JSON as text) | search_ebay, eBay_deep_scan, ebook_deep_scan, search_amazon, search_craigslist, search_google, open_ledger, code_interpreter, fetch_page, search, connect_to_mcp |
| Chinese/Thai text leakage | 0 (no tool execution) | 2 runs (prompts #1 R1, R2: 湾仔) |
| Chain gating blocks | 0 (no tool execution) | ~15 instances across all runs |

## Comparison with Non-Abliterated Baselines

| Metric | qwen2.5:14b | coder-abliterate:14b | qwen3:14b | qwen3-abliterated:14b |
| --- | --- | --- | --- | --- |
| Tool calls | 120 | 0 | 119 | 171 |
| Execution rate | 98% | 0% | 97% | 97% |
| Avg time | 18.4s | 7.9s | 38.3s | 39.6s |

**Verdict:** The coder-abliterate variant is completely broken for tool calling — qwen-agent cannot parse its output format. The qwen3-abliterated variant performs similarly to the base qwen3:14b in execution rate but with significantly more hallucinated tool names and higher tool call volume (171 vs 119), indicating less efficient tool use.

---

## Per-Prompt Scorecards

### Prompt #1 — eBay Search (single platform)

> Search eBay for "Sony WH-1000XM5" headphones under $200 and show me the top 5 results sorted by price.

**Expected:** `ecommerce_search` with platform=ebay (or `ebay_deep_scan`)

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 — emitted JSON as text (`<tool>`, `<result>`, `<function>`) | R1: `cross_platform_search` x2, R2: `ebay_deep_scan` x2, R3: `ebay_deep_scan` x1 |
| Useful response? | No — raw JSON in response body | R1-R2: Chinese text (湾仔), R3: chain gating error |
| Avg time | 8.2s | 71.6s |
| **Score** | **F** — zero tool execution | **D** — tools fire but Chinese text leakage, no useful English response |

**Issues:** qwen3-abliterated responds in Chinese after receiving eBay results. Chain gating blocks R3 (`ebay_deep_scan` not ready). Neither model uses `ecommerce_search`.

---

### Prompt #2 — Cross-Platform Deals

> Find me the best deals on a used ThinkPad T480 — check eBay, Amazon, and Craigslist.

**Expected:** `cross_platform_search` or `deal_finder`

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 — text JSON with `<start>`, `<function>` wrappers | R1: `ecommerce_search` x4, R2: `cross_platform_search` x2, R3: hallucinated `search_ebay`, `search_amazon`, `search_craigslist`, `search_google` |
| Useful response? | No | R1: told user to use deal_finder (didn't use it). R2: good Craigslist prices by city. R3: hallucinated tools failed. |
| Avg time | 6.8s | 66.1s |
| **Score** | **F** | **C-** — R2 produced useful data, others broken |

**Issues:** R1 used `ecommerce_search` 4 times instead of `cross_platform_search` once. R3 hallucinated old removed tool names.

---

### Prompt #3 — eBay Sold Listings

> What have Sony WH-1000XM5 headphones actually sold for on eBay recently?

**Expected:** `ecommerce_search` with platform=ebay_sold (or `ebay_deep_scan`)

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 | R1: `ebay_deep_scan` x2 + `trial_balance` (wrong). R2: `ebay_deep_scan` x2. R3: `eBay_deep_scan` (wrong case). |
| Useful response? | No | R1: returned trial balance data (wrong tool). R2: confused about trial_balance params. R3: tool name case error. |
| Avg time | 6.4s | 21.4s |
| **Score** | **F** | **D** — tools fire but wrong tools called (trial_balance for eBay query), case sensitivity error |

**Issues:** R1 called `trial_balance` for an eBay price lookup — chain gating redirected to accounting tools. R3 used `eBay_deep_scan` (capital E) which doesn't exist.

---

### Prompt #4 — Craigslist Multi-City

> Search Craigslist in Portland and Seattle for standing desks under $150.

**Expected:** `ecommerce_search` with platform=craigslist and cities

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 | R1-R2: `cross_platform_search` x1 each (chain gated). R3: `cross_platform_search` + hallucinated `search`. |
| Useful response? | No | R1-R2: chain gating "not ready" errors. R3: told user "search" tool exists (it doesn't). |
| Avg time | 6.4s | 17.5s |
| **Score** | **F** | **F** — 0/3 useful, chain gating blocks all attempts |

**Issues:** Chain gating prevents `cross_platform_search` from executing — says previous step not complete. This is a false dependency.

---

### Prompt #5 — Create Ledger

> Set up a new ledger for me and show me the default chart of accounts.

**Expected:** `create_ledger` → `list_accounts`

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 | R1: `create_ledger` x2. R2: `create_ledger` x4 + `open_ledger` x2 + `mark_task_done`. R3: `create_ledger` x2 + `open_ledger` x2. |
| Useful response? | No | R1: "already have ledger ID 15". R2-R3: hallucinated `open_ledger` tool. |
| Avg time | 9.2s | 26.6s |
| **Score** | **F** | **C-** — correctly identifies existing ledger but hallucinated `open_ledger`, never calls `list_accounts` |

**Issues:** `open_ledger` doesn't exist — model hallucinates it repeatedly. Never reaches `list_accounts` to show chart of accounts.

---

### Prompt #6 — Journal Entry (Rent)

> I paid $1,200 rent today from the business checking account. Record that as a journal entry for March 27, 2026.

**Expected:** `journalize_transaction`

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 | R1: 6 calls (journalize + inventory tools). R2: 14 calls (journalize + inventory + account_ledger). R3: 9 calls. |
| Useful response? | No | All 3 runs: spammed `mark_task_done` with wrong task numbers, called inventory tools for a rent payment. |
| Avg time | 10.8s | 82.7s |
| **Score** | **F** | **D-** — excessive tool calls (6-14 per run), called inventory tools for a rent payment, wrong task numbers |

**Issues:** Model conflates accounting tasks — calls `journalize_fifo_transaction`, `list_inventory_items`, `receive_inventory` for a simple rent payment. `mark_task_done` fails with wrong task numbers.

---

### Prompt #7 — Inventory Purchase + Valuation

> Record a purchase: I bought 50 units of "Widget A" at $12 each on account. Then show me the current inventory valuation.

**Expected:** `register_inventory_item` → `receive_inventory` → `journalize_fifo_transaction` → `inventory_valuation`

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 | R1: 9 calls. R2: 2 calls. R3: 8 calls (includes `deactivate_inventory_item`). |
| Useful response? | No | R1: wrong task numbers. R2: Widget A not registered. R3: marked done but called `deactivate_inventory_item` along the way. |
| Avg time | 9.7s | 55.3s |
| **Score** | **F** | **D** — R3 eventually marks done, but approach is messy; R2 fails on unregistered item |

**Issues:** Model doesn't follow the correct sequence (register → receive → journalize → valuate). Calls `deactivate_inventory_item` during a purchase flow.

---

### Prompt #8 — Trial Balance + Income Statement

> Generate a trial balance and income statement for the current period.

**Expected:** `trial_balance` → `income_statement`

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 | R1: `account_ledger` x6. R2: `trial_balance` x2. R3: `account_ledger` + `void_transaction` x2. |
| Useful response? | No | R1: "All Accounts" doesn't exist. R2: balanced trial balance at $1,250. R3: tried to void entries. |
| Avg time | 9.1s | 48.1s |
| **Score** | **F** | **C** — R2 produces valid trial balance, R1 and R3 use wrong tools entirely |

**Issues:** R1 called `account_ledger` 6x trying to view "All Accounts". R3 called `void_transaction` — destructive operation for a reporting query. Only R2 used the correct tool.

---

### Prompt #9 — Web Search

> Search the web for "best self-hosted LLM frameworks 2026" and give me a summary of the top results.

**Expected:** `web_search` or `ddg_web_search`

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 | R1: `ddg_web_search` (chain gated). R2: `web_search` (chain gated). R3: no calls. |
| Useful response? | No | All 3: chain gating "not ready" errors or no tools called. |
| Avg time | 5.5s | 16.1s |
| **Score** | **F** | **F** — 0/3 useful, chain gating blocks web search tools |

**Issues:** Chain gating creates false dependency — web search tools gated behind unrelated chain steps. R3 says no web search tools exist.

---

### Prompt #10 — Fetch URL

> Fetch the page at https://ollama.com/library and list the available models.

**Expected:** `fetch_url` or `browser_fetch`

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 | R1: `browser_fetch` x2 (works). R2: `fetch_page` (hallucinated). R3: `browser_fetch` x2 (works). |
| Useful response? | No | R1, R3: good model listings. R2: hallucinated `fetch_page` tool name. |
| Avg time | 7.1s | 43.9s |
| **Score** | **F** | **B-** — 2/3 runs produce useful Ollama model listings, R2 hallucinated tool name |

---

### Prompt #11 — Directory Tree + Grep

> Show me the directory tree of the current project, then find all Python files that import from qwen_agent.

**Expected:** `tree` → `grep`

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 | R1-R2: `tree` x2 (1 result each). R3: `tree` + `grep` + `tree` (1 result). |
| Useful response? | No | All 3: empty responses despite tool calls. |
| Avg time | 8.8s | 11.9s |
| **Score** | **F** | **D-** — tools fire but no visible output, never completes grep step in R1-R2 |

**Issues:** Model calls `tree` twice but doesn't proceed to `grep`. Results are empty strings.

---

### Prompt #12 — Codebase Search

> Search the codebase for any function that references "conversation_id" and list the files.

**Expected:** `grep` or `find`

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 | R1: `code_interpreter` + `ls` (hallucinated + chain gated). R2: `find` + `definition` x2. R3: `code_interpreter` + `mark_task_done`. |
| Useful response? | No | R1: chain gating error. R2: empty. R3: hallucinated file list (conversation_manager.py, etc. — don't exist). |
| Avg time | 8.8s | 24.8s |
| **Score** | **F** | **F** — R3 fabricated file names, R1 hallucinated `code_interpreter`, R2 empty |

**Issues:** Model hallucinates `code_interpreter` tool. R3 fabricates non-existent filenames. Never uses `grep` which is the correct tool.

---

### Prompt #13 — Multi-Task (eBay + Accounting)

> I need to do two things: search eBay for "RTX 4070" GPUs under $400, and also record a $50 office supplies purchase in the ledger dated today.

**Expected:** `ebay_deep_scan` + `journalize_transaction`

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 | R1: 3 calls. R2: 7 calls (chain gated: `account_ledger` depends on `ebay_deep_scan`). R3: 5 calls (`create_ledger` x4). |
| Useful response? | No | R1: wrong task number. R2: chain gating creates false eBay→accounting dependency. R3: retries create_ledger. |
| Avg time | 8.9s | 49.4s |
| **Score** | **F** | **D-** — chain gating creates absurd dependency (account_ledger blocked by ebay_deep_scan) |

**Issues:** **This is the chain gating bug at its worst** — the planner links `ebay_deep_scan` and `account_ledger` into the same chain, so the accounting tool is gated behind the ecommerce tool completing.

---

### Prompt #14 — Follow-up: Execute Tasks

> Go ahead and do the tasks.

**Expected:** Execute pending tasks from prompt #13

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 | R1: 5 calls (hallucinated `search_ebay`). R2: 1 call (chain gated). R3: 2 calls (`search_ebay` + `receive_inventory`). |
| Useful response? | No | R1: `search_ebay` doesn't exist. R2: chain gating blocks `ebay_deep_scan`. R3: `search_ebay` doesn't exist. |
| Avg time | 7.8s | 27.0s |
| **Score** | **F** | **F** — 0/3 useful, hallucinated tool names + chain gating |

---

### Prompt #15 — Cross-Domain (eBay Price + Ledger Check)

> Look up the current price of a used Herman Miller Aeron on eBay, then check if we have enough cash in the ledger to buy one.

**Expected:** `ebay_deep_scan` → `get_account_balance`

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 | R1: `ebook_deep_scan` x2 (typo). R2: `ebay_deep_scan` x2 (works). R3: `browser_fetch` + `ebay_deep_scan` (chain gated). |
| Useful response? | No | R1: `ebook_deep_scan` doesn't exist. R2: got eBay data but exposed `<think>` tags. R3: chain gating. |
| Avg time | 6.2s | 37.7s |
| **Score** | **F** | **D** — R2 partially works but leaks thinking tags, never checks ledger balance |

**Issues:** `ebook_deep_scan` typo (R1). None of the runs reach `get_account_balance` for the second part of the task.

---

### Prompt #16 — Tool Listing (Knowledge)

> What tools do you have available?

**Expected:** No tool calls needed — answer from system prompt.

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 | R1-R2: 0 calls (correct!). R3: 4 calls including `connect_to_mcp` x3. |
| Useful response? | No (listed JSON tool calls as text) | R1: decent list. R2: hallucinated tools (save, load). R3: called connect_to_mcp then marked done. |
| Avg time | 5.7s | 21.9s |
| **Score** | **F** | **C** — R1 good, R2 hallucinates tool names, R3 calls unnecessary tools |

---

### Prompt #17 — Knowledge (Double-Entry Bookkeeping)

> Explain how double-entry bookkeeping works.

**Expected:** No tool calls — pure knowledge answer.

| | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Tool calls? | 0 (correct!) | R1: 11 calls (create_account + account_ledger). R2: 5 calls (balance_sheet + income_statement). R3: 3 calls (balance_sheet + trial_balance + close_period). |
| Useful response? | **Yes** — clear explanation of double-entry bookkeeping | R1: "create the account first". R2: generated income statement. R3: closed a period. |
| Avg time | 7.6s | 51.9s |
| **Score** | **B** — good text response (only working prompt) | **F** — used tools unnecessarily for a knowledge question, R3 called `close_period` (destructive!) |

**Issues:** qwen3-abliterated cannot answer knowledge questions without calling tools. R3 calling `close_period` is destructive and wrong.

---

## Summary by Category

| Category | coder-abliterate:14b | qwen3-abliterated:14b |
| --- | --- | --- |
| Ecommerce (#1-4) | F (0/4 tool execution) | D (chain gating + Chinese text + hallucinated names) |
| Accounting (#5-8) | F (0/4 tool execution) | C- (R2 of #8 good, rest messy) |
| Web (#9-10) | F | D (1 of 2 prompts partially works) |
| Filesystem (#11-12) | F | F (empty responses, hallucinated tools) |
| Multi-Domain (#13-15) | F | D- (chain gating creates false cross-domain deps) |
| Knowledge (#16-17) | C (text answer works for #17) | D (calls tools for knowledge questions) |

---

## Chain Gating: Root Cause Analysis

The chain gating system (`ChainedAssistant` + `Toolchain`) is the single biggest issue affecting the qwen3-abliterated results. Here's what's happening:

### How It Works

1. The **chain planner** (1.7B model) receives task titles and builds tool chains — ordered sequences of tool calls where each step depends on the previous step's output.
2. The **ChainedAssistant** intercepts every `_call_tool()` and checks:
   - Is this tool in a chain? If yes, is it the current step? If not → **blocked with "not ready" error**.
   - Is the current step ready (previous step completed)? If not → **blocked**.
3. Tools NOT in any chain pass through normally.

### Why It Breaks

**Problem 1: False cross-domain dependencies.** The 1.7B chain planner puts unrelated tools into the same chain. Example from Prompt #13:
- Task: "search eBay for RTX 4070 + record office supplies purchase"
- Planner chains: `ebay_deep_scan` → `account_ledger`
- Result: accounting tools are blocked until eBay search completes

**Problem 2: Single-tool chains create unnecessary gating.** Even for prompts that need just one tool (e.g., `web_search`), the planner creates a chain with that tool, causing it to be gated behind a nonexistent "previous step."

**Problem 3: Chain gating applies globally.** If tool X appears in ANY chain for ANY task in the conversation, ALL calls to tool X are gated — even if the user's current request has nothing to do with that chain's task.

**Problem 4: The planner hallucinates chains.** The 1.7B model sometimes creates chains with tools that don't exist or chains that make no logical sense (e.g., `trial_balance` after `ebay_deep_scan`).

### Impact on Scores

- Prompts #4, #9: web/ecommerce tools chain-gated with "not ready" across all runs
- Prompt #13: accounting tools falsely depend on ecommerce completion
- Prompt #14: follow-up fails because chain state from #13 is broken
- Prompt #15: cross-domain task blocked by chain dependencies

### Recommended Fix

The chain gating adds complexity that actively hurts tool execution for abliterated models. Options:

1. **Disable chain gating entirely** — let the main model decide tool order. The 14B model is capable of sequencing tools without a state machine enforcing order.
2. **Only gate within the same domain** — don't chain tools across categories (ecommerce → accounting should never be a single chain).
3. **Make gating advisory, not blocking** — return the suggested order as a hint in the response but don't block execution.
4. **Fix the 1.7B planner** — prevent it from creating cross-domain chains and single-tool chains.

---

## Top Issues to Fix (Priority Order)

1. **coder-abliterate:14b tool format incompatibility** — model outputs tool calls as XML/JSON text that qwen-agent can't parse. This model is unusable with qwen-agent's `Assistant.run()` without a custom parser.
2. **Chain gating false dependencies** — the #1 issue for qwen3-abliterated. Blocks correct tool calls across all categories.
3. **Hallucinated tool names** — qwen3-abliterated invents: `search_ebay`, `eBay_deep_scan`, `ebook_deep_scan`, `open_ledger`, `code_interpreter`, `fetch_page`, `search_google`, `search`. System prompt tool listing isn't preventing this.
4. **Chinese text leakage** — qwen3-abliterated responds in Chinese after receiving tool results (prompts #1 R1-R2).
5. **Unnecessary tool calls for knowledge questions** — qwen3-abliterated calls 3-11 tools for "explain bookkeeping" instead of answering directly.
6. **Destructive tool calls** — `void_transaction` (#8 R3) and `close_period` (#17 R3) called during read-only tasks.
7. **`<think>` tag leakage** — qwen3-abliterated exposes internal reasoning tags in responses (#15 R2).
