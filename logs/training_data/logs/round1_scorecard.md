# Round 1 Scorecard — qwen2.5:14b vs qwen3:14b

Test date: 2026-03-28 | 3 runs per prompt per model | 17 prompts

## Overall

| Metric | qwen2.5:14b | qwen3:14b |
|--------|-------------|-----------|
| Total tool calls | 120 | 119 |
| Total tool results | 117 | 116 |
| **Execution rate** | **98%** | **97%** |
| Avg time/prompt | 18.4s | 38.3s |
| Hallucinated tool names | 6 instances | 8 instances |
| Text-as-tool-call (leaked `</tool_call>`) | 3 runs | 0 runs |

---

## Per-Prompt Scorecards

### Prompt #1 — eBay Search (single platform)
> Search eBay for "Sony WH-1000XM5" headphones under $200 and show me the top 5 results sorted by price.

**Expected:** `ecommerce_search` with platform=ebay (or `ebay_deep_scan`). Task extraction → Ecommerce group.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | Ecommerce 3/3 | Ecommerce 3/3 |
| Correct tool? | Run 1: `ebay_deep_scan` + unrelated inventory tools. Run 2: `ebay_deep_scan` x2. Run 3: `ebay_search` (removed tool). | Run 1: `ebay_deep_scan`. Run 2-3: `ebay_deep_scan` x2. |
| Useful response? | Run 2 good (28 items, price range). Runs 1,3 off-target. | Run 2 best (specific prices $162.99). Run 1 error. |
| Avg time | 30.8s | 64.0s |
| **Score** | **C** — inconsistent; Run 1 called inventory tools for an eBay search | **B** — Run 2 excellent, others degraded |

**Issues:** Both models call `ebay_deep_scan` instead of the new `ecommerce_search`. Old `ebay_search` name still hallucinated (qwen2.5 Run 3). Chain gating interferes — Run 1 qwen2.5 went off the rails with inventory tools. Need to update round1_prompts.md to expect `ecommerce_search`.

---

### Prompt #2 — Cross-Platform Deals
> Find me the best deals on a used ThinkPad T480 — check eBay, Amazon, and Craigslist.

**Expected:** `cross_platform_search` or `deal_finder`. Task extraction → Ecommerce group.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | Ecommerce 3/3 | Ecommerce 3/3 |
| Correct tool? | Run 1: `cross_platform_search` x2 (correct!). Runs 2-3: emitted tool call as raw text with Chinese prefix. | All 3 runs failed — said tools don't exist or hallucinated names. |
| Useful response? | Run 1 good (Craigslist deals listed). Runs 2-3 broken. | 0/3 useful. |
| Avg time | 43.2s | 13.3s |
| **Score** | **D+** — 1/3 worked, 2/3 text leakage | **F** — 0/3, model doesn't recognize the tool |

**Issues:** qwen2.5 text leakage (`煋`, `范冰XML`). qwen3 doesn't recognize `cross_platform_search` exists even though it's in the function list. Both models struggle with this tool name.

---

### Prompt #3 — eBay Sold (market price)
> What have Sony WH-1000XM5 headphones actually sold for on eBay recently? I want to know the real market price.

**Expected:** `ecommerce_search` with platform=ebay_sold. Task extraction → Ecommerce group.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | Ecommerce 3/3 | Ecommerce 2/3 |
| Correct tool? | All 3: `ebay_deep_scan` x2 (close but not sold listings). | Runs 1-2: `ebay_deep_scan` x2. Run 3: no tools. |
| Useful response? | Run 1 excellent (47 listings, price stats). Runs 2-3: empty query errors. | All 3 returned errors or no data. |
| Avg time | 22.0s | 22.5s |
| **Score** | **C+** — Run 1 great, others empty query bug | **D** — tools executed but all errored |

**Issues:** Neither model knows to use `ebay_sold` mode. `ebay_deep_scan` searches active listings, not completed sales. Chain gating may be sending empty query params. The new `ecommerce_search` with `platform=ebay_sold` should fix this if models learn the param.

---

### Prompt #4 — Craigslist Multi-City
> Search Craigslist in Portland and Seattle for standing desks under $150.

**Expected:** `ecommerce_search` with platform=craigslist, cities=["portland","seattle"]. Task extraction → Ecommerce group.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | Ecommerce 2/3 | Ecommerce 2/3 |
| Correct tool? | Run 1: `search_craigslist` (hallucinated). Run 2: `cross_platform_search` (worked!). Run 3: `cross_platform_search` (chain error). | Run 1: `cross_platform_search` (chain error). Runs 2-3: gave up, said no tools. |
| Useful response? | Run 2 excellent (standing desks from multiple cities with prices). Others failed. | 0/3 useful. |
| Avg time | 40.8s | 17.2s |
| **Score** | **D+** — 1/3 worked beautifully | **F** — 0/3, model gives up too easily |

**Issues:** Chain gating blocking `cross_platform_search` — "not the current step in its chain." qwen3 interprets chain errors as "tool doesn't exist" and gives up. The new `ecommerce_search` with cities param is a simpler path that avoids cross_platform_search chain issues.

---

### Prompt #5 — Create Ledger
> Set up a new ledger for me and show me the default chart of accounts.

**Expected:** `create_ledger` → `list_accounts`. Task extraction → Accounting group.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | Accounting 3/3 | Accounting 3/3 |
| Correct tool? | All 3: `create_ledger` + `list_accounts` (correct chain!). But also retried `create_ledger` after error. | All 3: `create_ledger`. Only Run 2 tried `trial_balance`. |
| Useful response? | All 3 correctly reported "ledger already exists (id=15)." | All 3 correctly reported existing ledger. |
| Avg time | 12.0s | 25.6s |
| **Score** | **B** — correct tools, correct error handling, retried unnecessarily | **B-** — correct error handling but didn't attempt list_accounts |

**Issues:** Pre-existing ledger (id=15) blocks the test. Both models handle the error gracefully. qwen2.5 correctly tries `list_accounts` as second step. Need to reset ledger state between test runs, or change prompt to "Show me my ledger and chart of accounts."

---

### Prompt #6 — Journal Entry
> I paid $1,200 rent today from the business checking account. Record that as a journal entry for March 27, 2026.

**Expected:** `journalize_transaction` with debit Rent Expense $1200, credit Cash $1200.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | Accounting 1/3 | Accounting 2/3 |
| Correct tool? | Run 1: 7 tools including wrong ones (`journalize_fifo_transaction`). Run 2: `account_ledger` only. Run 3: `journalize_transaction` (correct!). | Runs 1-2: `journalize_transaction` (correct!) + extras. Run 3: `journalize` (hallucinated short name). |
| Useful response? | Run 1: error cascade. Run 2: showed empty ledger. Run 3: parameter error on `lines`. | Run 1: parameter errors. Run 2: inventory item error. Run 3: explained function doesn't exist. |
| Avg time | 40.9s | 35.8s |
| **Score** | **D** — correct tool 1/3 but params always wrong | **D** — correct tool 2/3 but params always wrong |

**Issues:** Both models identify `journalize_transaction` but can't construct the `lines` parameter correctly (array of debit/credit objects). The schema for journal lines is complex. Models also confuse it with `journalize_fifo_transaction`. This tool needs a simpler parameter interface or better description.

---

### Prompt #7 — Inventory Purchase + Valuation
> Record a purchase: I bought 50 units of "Widget A" at $12 each on account. Then show me the current inventory valuation.

**Expected:** `register_inventory_item` → `receive_inventory` → `inventory_valuation` chain.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | Accounting 2/3 | Accounting 2/3 |
| Correct tool? | Runs 1-2: `journalize_transaction` + `inventory_valuation` (partial). Run 3: `inventory_valuation` + `mark_task_done` loop. | Run 1: `journalize_transaction` x2 (wrong). Run 2: `receive_inventory` chain (correct!). Run 3: `receive_inventory` → `inventory_valuation` → `journalize_fifo_transaction` (close). |
| Useful response? | Run 1: reported FIFO sale (wrong direction). Run 2: showed valuation. Run 3: partial. | Run 2: successful inventory receipt (100 units @ $5). Run 3: partial chain completion. |
| Avg time | 19.0s | 50.7s |
| **Score** | **C-** — got valuation data but wrong tool chain | **C** — Run 2 correct chain, others confused |

**Issues:** Models mix up `journalize_transaction`, `receive_inventory`, and `journalize_fifo_transaction`. The correct flow (register → receive → value) is rarely followed. qwen3 Run 2 was closest to correct.

---

### Prompt #8 — Trial Balance + Income Statement
> Generate a trial balance and income statement for the current period.

**Expected:** `trial_balance` + `income_statement`. Task extraction → Accounting.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | Accounting 3/3 | Accounting 3/3 |
| Correct tool? | Run 1: `trial_balance` only. Runs 2-3: both tools (correct!). | Run 1: `trial_balance` + `income_statement` + `balance_sheet` (extra). Run 2: `trial_balance` + `balance_sheet`. Run 3: started with `create_ledger` (wrong). |
| Useful response? | All 3 returned actual financial data (Cash $500, balanced). | Runs 1-2 returned real data. Run 3 had chain confusion. |
| Avg time | 16.8s | 60.2s |
| **Score** | **B+** — correct tools, real data, well-formatted | **B** — correct tools mostly, but added extras and Run 3 went sideways |

**Issues:** Both do well here. qwen3 adds `balance_sheet` which wasn't asked for but isn't wrong. The data is real and balanced (Cash $500, total assets = total equity).

---

### Prompt #9 — Web Search
> Search the web for "best self-hosted LLM frameworks 2026" and give me a summary of the top results.

**Expected:** `ddg_web_search`. Task extraction → Web Tools.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | Web Tools 1/3 | Web Tools 1/3 |
| Correct tool? | Run 1: emitted as text. Run 2: `ddg_web_search` (correct!). Run 3: `web_search` (hallucinated). | Run 1: `ddg_web_search` (correct!). Run 2: no tools. Run 3: hallucinated `search_web`, `search`, `search_tools`. |
| Useful response? | Run 2: recognized tool but said it wasn't available. | Run 1: same — executed but said not available. Run 2: gave knowledge-based answer. |
| Avg time | 8.0s | 19.5s |
| **Score** | **D** — correct tool 1/3, text leakage, curation weak | **D** — correct tool 1/3, hallucinated names, curation weak |

**Issues:** Curation only recommends Web Tools 1/3 times — task extractor may not be recognizing web search tasks. Both models find `ddg_web_search` sometimes but then say it's "not available" — possibly chain gating or tool-name mismatch. qwen3 hallucinates multiple search tool names.

---

### Prompt #10 — Browser Fetch
> Fetch the page at https://ollama.com/library and list the available models.

**Expected:** `browser_fetch`. Task extraction → Web Tools.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | Web Tools 3/3 | Web Tools 3/3 |
| Correct tool? | All 3: `browser_fetch` x2 (correct!). | Runs 1-2: `browser_fetch` x2. Run 3: `browser_fetch` + `code_interpreter` (hallucinated). |
| Useful response? | All 3 excellent — listed models with pull counts and descriptions. | Runs 1-2 excellent (structured JSON model lists). Run 3: chain error on `code_interpreter`. |
| Avg time | 18.9s | 53.6s |
| **Score** | **A** — 3/3 correct, useful, well-formatted | **A-** — 2/3 excellent, Run 3 derailed by hallucinated tool |

**Issues:** Best-performing prompt for both models. `browser_fetch` is well-understood. The double-call pattern (fetch then fetch again) suggests the model wants to paginate or re-parse.

---

### Prompt #11 — Directory Tree + Grep
> Show me the directory tree of the current project, then find all Python files that import from qwen_agent.

**Expected:** `tree` → `grep`. Task extraction → Filesystem + Code Search.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | Filesystem+Code Search 2/3 | Filesystem+Code Search 2/3 |
| Correct tool? | Runs 1-2: `tree` x2 (partially correct, missing grep). Run 3: hallucinated `show_directory_tree`. | Run 1: `tree` + `grep` (correct!). Run 2: `tree` x2. Run 3: no tools. |
| Useful response? | Runs 1-2: empty. Run 3: error. | Run 1: tree result but empty response. Run 3: said tools don't exist. |
| Avg time | 10.1s | 22.8s |
| **Score** | **D-** — called tree but never grep, empty responses | **D** — Run 1 correct tools but no final output |

**Issues:** Both models call `tree` but struggle to chain `grep` afterward. Responses are empty even when tools return data — the model may not be synthesizing the tool results into a user-facing answer. qwen3 Run 3 gives up entirely.

---

### Prompt #12 — Code Search
> Search the codebase for any function that references "conversation_id" and list the files.

**Expected:** `grep` or `search_codebase`. Task extraction → Code Search.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | Web Tools 1/3 (wrong group) | Code Search 2/3 |
| Correct tool? | Run 1: `code_interpreter` (wrong). Run 2: no tools. Run 3: `browser_fetch` (very wrong). | Run 1: `search_codebase` (hallucinated but close). Run 2: `search_codebase_for_string` (hallucinated). Run 3: `grep` (correct!). |
| Useful response? | 0/3 useful. | Run 3 closest — tried grep but got chain error. |
| Avg time | 10.2s | 26.9s |
| **Score** | **F** — wrong tools, wrong curation group | **D** — correct intent, hallucinated names, 1/3 correct tool |

**Issues:** qwen2.5 curates as "Web Tools" instead of "Code Search" — task extractor bug. Both models struggle with the actual tool name (`grep` vs `search_codebase`). The `grep` tool exists but chain gating may block it.

---

### Prompt #13 — Multi-Domain (eBay + Ledger)
> I need to do two things: search eBay for "RTX 4070" GPUs under $400, and also record a $50 office supplies purchase in the ledger dated today.

**Expected:** Two tasks extracted. Ecommerce + Accounting groups. Multi-tool execution.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | Ecommerce 1/3 (missing Accounting) | Ecommerce+Accounting 2/3 |
| Correct tools? | Mixed — `cross_platform_search`, `ebay_deep_scan`, `account_ledger`, `journalize_fifo_transaction`. | Run 3: 15 calls across many tools (overactive). Runs 1-2: 2-3 calls. |
| Useful response? | 0/3 completed both tasks. | 0/3 completed both tasks. |
| Avg time | 15.5s | 78.4s |
| **Score** | **D** — identified tools but couldn't execute either task | **D+** — better curation but Run 3 went haywire (15 calls) |

**Issues:** Multi-task is the hardest category. qwen2.5 only curates Ecommerce (misses Accounting). qwen3 Run 3 made 15 tool calls without completing either task — a sign of confusion. Neither model can construct correct params for journalize or inventory tools.

---

### Prompt #14 — Follow-up ("Go ahead")
> Go ahead and do the tasks.

**Expected:** Zero new task extraction. Execute pending tasks from prompt 13's conversation.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | Ecommerce+Accounting 2/3 | Varied |
| Correct behavior? | All 3 attempted tool calls (correct — should execute). But called wrong tools. | Run 1: no calls (said no tasks). Runs 2-3: attempted execution. |
| Useful response? | Run 1 closest — `ebay_deep_scan` + `register_inventory_item`. Others had errors. | Run 2: listed inventory items. Run 3: account errors. |
| Avg time | 13.2s | 30.4s |
| **Score** | **C-** — attempted execution, wrong tool params | **D** — Run 1 gave up, others tried but failed |

**Issues:** qwen3 Run 1 doesn't see the tasks from the conversation context. Task persistence across the follow-up works for qwen2.5 but not consistently for qwen3.

---

### Prompt #15 — Cross-Domain Chain (eBay → Accounting)
> Look up the current price of a used Herman Miller Aeron on eBay, then check if we have enough cash in the ledger to buy one.

**Expected:** `ecommerce_search` (ebay) → `account_ledger` (Cash) or `get_account_balance`. Cross-domain reasoning.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | Ecommerce 2/3, Web+Accounting 1/3 | Ecommerce 2/3, Ecommerce+Accounting 1/3 |
| Correct tools? | Runs 1,3: `ebay_deep_scan` + `account_ledger` (correct pair!). Run 2: `browser_fetch` x2. | Runs 1-2: `ebay_deep_scan` + `account_ledger` x2 each (correct!). Run 3: `account_ledger` only. |
| Useful response? | Runs 1,3: chain dependency error between the two tools. Run 2: fetched eBay HTML. | Runs 1-2 excellent — eBay data + ledger data, business recommendation. Run 3: chain error. |
| Avg time | 14.9s | 60.2s |
| **Score** | **C** — correct tool pair but chain gating blocks cross-domain | **B+** — Runs 1-2 fully completed both steps with useful synthesis |

**Issues:** Chain gating creates a false dependency — `account_ledger` "waits for" `ebay_deep_scan` even though they're independent. qwen3 Runs 1-2 somehow bypass this and deliver excellent cross-domain answers with purchase recommendations.

---

### Prompt #16 — Meta: List Tools
> What tools do you have available?

**Expected:** Text response listing tools. No tool calls needed. Curator "pass" path.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | None 3/3 (pass — correct) | MCP 1/3, None 2/3 |
| Correct behavior? | All 3 called tools unnecessarily. | Runs 2-3: text-only response (correct!). Run 1: called `connect_to_mcp`. |
| Useful response? | Run 2: marked task as done (wrong). Runs 1,3: called non-existent tools. | Runs 2-3: comprehensive tool list in text (excellent!). |
| Avg time | 15.6s | 25.0s |
| **Score** | **F** — should not call tools for this prompt | **B+** — 2/3 answered in text correctly |

**Issues:** qwen2.5 reflexively calls tools even for meta questions. qwen3 is smarter — recognizes this is a knowledge question and answers from its understanding of the tool list. qwen2.5 needs system prompt guidance: "If the user asks about your capabilities, answer from your tool descriptions without calling tools."

---

### Prompt #17 — Knowledge: Double-Entry Bookkeeping
> Explain how double-entry bookkeeping works.

**Expected:** Text response explaining concepts. No tool calls needed. Curator "pass" path.

| | qwen2.5:14b | qwen3:14b |
|---|---|---|
| Curation | Accounting 3/3 (wrong — should be pass) | Accounting 3/3 (wrong — should be pass) |
| Correct behavior? | All 3 called accounting tools (unnecessary). | Run 1: text-only (correct!). Runs 2-3: called tools. |
| Useful response? | All 3 showed real balance sheet data — useful but not what was asked. | Run 1: clear explanation of debits/credits (excellent!). Run 3: 14 calls, 194s (way overboard). |
| Avg time | 15.2s | 89.5s |
| **Score** | **D** — showed data instead of explaining concepts | **C** — Run 1 perfect, Run 3 disastrous (14 calls for a knowledge question) |

**Issues:** Curator recommends Accounting for both models — it should "pass" for knowledge questions. qwen3 Run 3 made 14 alternating `balance_sheet`/`income_statement` calls for 194s — chain gating loop between the two tools. The curator's task extractor needs to distinguish "do accounting" from "explain accounting."

---

## Summary by Category

| Category | qwen2.5:14b | qwen3:14b | Notes |
|----------|-------------|-----------|-------|
| **Ecommerce (#1-4)** | D+ | D | Both struggle. `ecommerce_search` not yet known. Chain gating blocks. |
| **Accounting (#5-8)** | B- | B- | Correct tools identified. Params wrong for journal entries. Trial balance works. |
| **Web (#9-10)** | B- | B- | browser_fetch excellent. ddg_web_search flaky. Curation inconsistent. |
| **Filesystem (#11-12)** | D- | D | tree works, grep doesn't chain. Code search hallucinated. |
| **Multi-domain (#13-15)** | D+ | C- | Hardest category. qwen3 #15 was standout. Chain gating hurts. |
| **Conversational (#16-17)** | D- | B- | qwen3 answers knowledge Qs in text. qwen2.5 calls tools reflexively. |

## Top Issues to Fix

1. **Chain gating creates false dependencies** — `account_ledger` blocked by unrelated `ebay_deep_scan`. Independent tools should not be chained.
2. **Models don't know `ecommerce_search`** — still calling old tool names (`ebay_search`, `ebay_deep_scan`, `search_craigslist`). Need retraining or stronger system prompt guidance.
3. **`journalize_transaction` params too complex** — the `lines` array schema is hard for 14B models. Consider a simplified wrapper.
4. **Curator over-recommends tools for knowledge questions** — "Explain bookkeeping" shouldn't trigger Accounting group.
5. **qwen2.5 text leakage** — Chinese/Thai prefix before tool call JSON in ~6% of runs. Abliteration artifact.
6. **qwen3 gives up too easily** — when a tool returns an error, qwen3 often says "this tool doesn't exist" and stops. qwen2.5 retries more aggressively.
7. **Empty responses after tool execution** — tools return data but the model doesn't synthesize it into a user-facing answer (especially #11).
