# Round 1 — Baseline Test Prompts

Consistent style: natural, direct user requests. Each prompt targets a specific pipeline path.

## Ecommerce

| # | Prompt | Tests |
|---|--------|-------|
| 1 | Search eBay for "Sony WH-1000XM5" headphones under $200 and show me the top 5 results sorted by price. | Single tool, ebay_search |
| 2 | Find me the best deals on a used ThinkPad T480 — check eBay, Amazon, and Craigslist. | cross_platform_search / deal_finder |
| 3 | What have Sony WH-1000XM5 headphones actually sold for on eBay recently? I want to know the real market price. | ebay_sold_search |
| 4 | Search Craigslist in Portland and Seattle for standing desks under $150. | craigslist_multi_search |

## Accounting

| # | Prompt | Tests |
|---|--------|-------|
| 5 | Set up a new ledger for me and show me the default chart of accounts. | create_ledger + list_accounts chain |
| 6 | I paid $1,200 rent today from the business checking account. Record that as a journal entry for March 27, 2026. | journalize_transaction (debit Rent Expense, credit Cash) |
| 7 | Record a purchase: I bought 50 units of "Widget A" at $12 each on account. Then show me the current inventory valuation. | receive_inventory + inventory_valuation chain |
| 8 | Generate a trial balance and income statement for the current period. | trial_balance + income_statement chain |

## Web Tools

| # | Prompt | Tests |
|---|--------|-------|
| 9 | Search the web for "best self-hosted LLM frameworks 2026" and give me a summary of the top results. | ddg_web_search |
| 10 | Fetch the page at https://ollama.com/library and list the available models. | fetch_url or browser_fetch |

## Filesystem / Code Search

| # | Prompt | Tests |
|---|--------|-------|
| 11 | Show me the directory tree of the current project, then find all Python files that import from qwen_agent. | tree + grep chain |
| 12 | Search the codebase for any function that references "conversation_id" and list the files. | grep or find |

## Multi-domain

| # | Prompt | Tests |
|---|--------|-------|
| 13 | I need to do two things: search eBay for "RTX 4070" GPUs under $400, and also record a $50 office supplies purchase in the ledger dated today. | Multi-task extraction, multi-group curation |
| 14 | Go ahead and do the tasks. | Follow-up to 13. Should extract zero new tasks |
| 15 | Look up the current price of a used Herman Miller Aeron on eBay, then check if we have enough cash in the ledger to buy one. | Cross-domain chain (ecommerce -> accounting) |

## Conversational / Ambiguous

| # | Prompt | Tests |
|---|--------|-------|
| 16 | What tools do you have available? | Curator "pass" path, no tool needed |
| 17 | Explain how double-entry bookkeeping works. | Curator "pass" path, knowledge-only |

---

## Evaluation Checklist

After running all prompts, review:

- [ ] `logs/training_data/logs/task_extractor.jsonl` — check extraction accuracy
  - False positives (tasks extracted that shouldn't be)
  - Missed tasks (tasks that should have been extracted but weren't)
  - Duplicate handling (prompt 14 should produce `[]`)
- [ ] Chain planner logs — check tool chain quality
  - Correct tools selected for each task?
  - Sensible step ordering?
  - Parameter mappings correct (`$step_N.field` references)?
- [ ] Tool curation — check group recommendations
  - Right groups recommended for each prompt?
  - "pass" returned for prompts 16/17?
  - Prompts 13–14 run in same conversation (14 is a follow-up)
- [ ] Agent output quality — check final responses
  - Did the agent actually call the tools?
  - Were results presented clearly?
  - Any hallucinated data?

## Round 2 Notes

_Fill in after reviewing Round 1 outputs. Adjust prompt style based on what the 1.7B models struggled with._
