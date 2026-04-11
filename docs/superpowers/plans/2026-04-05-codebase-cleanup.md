# Codebase Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean root directory to ~15 items, refactor tools to Playwright MCP style, consolidate the pipeline into one package, fix the system prompt personality.

**Architecture:** Delete dead files, move pipeline modules into `pipeline/` package, move client stubs into `atomic_client/`, refactor tools in-place (merge duplicates, kill aliases/dispatchers, extract shared helpers). Update all imports. Update tests.

**Tech Stack:** Python, qwen-agent, Flask, SQLAlchemy, pytest

**Spec:** `docs/superpowers/specs/2026-04-04-codebase-cleanup-design.md`

---

## File Map

### New directories

- `pipeline/` — `__init__.py`, `gate.py`, `task_extractor.py`, `tool_curator.py`, `workflow_groups.py`
- `atomic_client/` — `__init__.py`, `agent.py`, `bridge.py`

### Files deleted

- `chained_assistant.py`, `chain_planner.py`, `Toolchain.py`, `toolchains.py`
- `checkpoints.db`, `checkpoints.db-shm`, `checkpoints.db-wal`
- `firebase-debug.log`, `main.css`, `claude_resume.txt`, `.zshrc`
- `get-agent.sh`, `get-agent.ps1`, `install_client.sh`, `install_client.ps1`
- `PROMPT.md`, `TIMELINE.md`, `TOOLS.md`, `README.md`
- `code_db/` (directory), `static/` (directory), `migrations/` (directory), `nginx/` (directory)

### Files moved/renamed

- `change_hats.py` → `pipeline/gate.py`
- `task_extractor.py` → `pipeline/task_extractor.py`
- `tool_curator.py` → `pipeline/tool_curator.py`
- `workflow_groups.py` → `pipeline/workflow_groups.py`
- `credentials.py` → `auth/credentials.py`
- `client_agent.py` → `atomic_client/agent.py`
- `client_bridge.py` → `atomic_client/bridge.py`

### Files modified in-place

- `tools/accounting.py` — kill aliases, merge FIFO/LIFO, extract DB boilerplate
- `tools/ecommerce.py` — kill dispatcher, merge eBay tools, merge CL tools, kill cross-platform
- `tools/onlyfans.py` — merge save_img/save_vid
- `tools/web.py` — fix www_cookies, extract validators
- `tools/__init__.py` — update if tool names change
- `main.py` — replace inline pipeline with `pipeline.process_message()`, rewrite system prompt
- `routes/tools.py` — update `workflow_groups` import
- `tests/test_task_extractor.py` — update import path
- `tests/test_tool_curator.py` — update import path
- `tests/test_workflow_groups.py` — update import path
- `tests/test_tools_ecommerce.py` — update for merged tools
- `tests/test_tools_web.py` — update for fixed www_cookies
- `CLAUDE.md` — update layout docs

---

### Task 1: Delete Dead Files

**Files:**
Delete: `chained_assistant.py`, `chain_planner.py`, `Toolchain.py`, `toolchains.py`
Delete: `checkpoints.db`, `checkpoints.db-shm`, `checkpoints.db-wal`
Delete: `firebase-debug.log`, `main.css`, `claude_resume.txt`, `.zshrc`
Delete: `get-agent.sh`, `get-agent.ps1`, `install_client.sh`, `install_client.ps1`
Delete: `PROMPT.md`, `TIMELINE.md`, `TOOLS.md`, `README.md`
Delete: `code_db/`, `static/`, `migrations/`, `nginx/`

- [✓] **Step 1: Delete dead Python files**

```bash
git rm chained_assistant.py chain_planner.py Toolchain.py toolchains.py
```

- [✓] **Step 2: Delete dead artifacts**

```bash
rm -f checkpoints.db checkpoints.db-shm checkpoints.db-wal firebase-debug.log main.css claude_resume.txt .zshrc
git rm --cached checkpoints.db checkpoints.db-shm checkpoints.db-wal firebase-debug.log main.css claude_resume.txt .zshrc 2>/dev/null || true
```

- [✓] **Step 3: Delete dead scripts and docs**

```bash
git rm get-agent.sh get-agent.ps1 install_client.sh install_client.ps1 PROMPT.md TIMELINE.md TOOLS.md README.md
```

- [✓] **Step 4: Delete dead directories**

```bash
git rm -r code_db/ static/ migrations/ nginx/
```

- [✓] **Step 5: Trim training data**

For each `.jsonl` in `training_data/logs/`, keep only first 100 lines:
```bash
for f in training_data/logs/*.jsonl; do
  head -100 "$f" > "$f.tmp" && mv "$f.tmp" "$f"
done
```
Delete dead training scripts:
```bash
rm -f training_data/round1_prompts.md training_data/run_prompts.py
```

- [✓] **Step 6: Verify nothing imports deleted files**

```bash
uv run python -c "import main" 2>&1
```
Expected: No `ModuleNotFoundError` for any deleted file. `chain_planner`, `Toolchain`, `toolchains`, `chained_assistant` are only imported by each other — not by `main.py` or any live code.

- [✓] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: delete dead files and artifacts from root"
```

---

### Task 2: Move Pipeline Files into `pipeline/` Package

**Files:**
- Create: `pipeline/__init__.py`
- Move: `change_hats.py` → `pipeline/gate.py`
- Move: `task_extractor.py` → `pipeline/task_extractor.py`
- Move: `tool_curator.py` → `pipeline/tool_curator.py`
- Move: `workflow_groups.py` → `pipeline/workflow_groups.py`
- Modify: `main.py` — update imports
- Modify: `routes/tools.py` — update imports
- Modify: `tests/test_task_extractor.py` — update imports
- Modify: `tests/test_tool_curator.py` — update imports
- Modify: `tests/test_workflow_groups.py` — update imports

- [✓] **Step 1: Create pipeline directory and move files**

```bash
mkdir -p pipeline
git mv change_hats.py pipeline/gate.py
git mv task_extractor.py pipeline/task_extractor.py
git mv tool_curator.py pipeline/tool_curator.py
git mv workflow_groups.py pipeline/workflow_groups.py
```

- [ ] **Step 2: Create `pipeline/__init__.py`**

```python
"""Recommendation pipeline — message classification, task extraction, tool curation."""
```

Just a docstring for now. The `process_message()` entry point comes in Task 7.

- [ ] **Step 3: Fix internal imports within pipeline files**

In `pipeline/gate.py`, update:
```python
# old
from workflow_groups import WORKFLOW_GROUPS, TOOL_REF, group_for_tool
# new
from pipeline.workflow_groups import WORKFLOW_GROUPS, TOOL_REF, group_for_tool
```

In `pipeline/tool_curator.py`, update:
```python
# old
from workflow_groups import WORKFLOW_GROUPS, TOOL_REF, tool_ref_for_group, group_for_tool
# new
from pipeline.workflow_groups import WORKFLOW_GROUPS, TOOL_REF, tool_ref_for_group, group_for_tool
```

- [✓] **Step 4: Update imports in `main.py`**

```python
# old
from change_hats import analyze_message
from workflow_groups import WORKFLOW_GROUPS, tools_for_groups, group_for_tool
# new
from pipeline.gate import analyze_message
from pipeline.workflow_groups import WORKFLOW_GROUPS, tools_for_groups, group_for_tool
```

- [✓] **Step 5: Update imports in `routes/tools.py`**

```python
# old
from workflow_groups import WORKFLOW_GROUPS
# new
from pipeline.workflow_groups import WORKFLOW_GROUPS
```

- [✓] **Step 6: Update test imports**

In `tests/test_task_extractor.py`:
```python
# old
from task_extractor import _build_extractor_prompt, _parse_extractor_response
# new
from pipeline.task_extractor import _build_extractor_prompt, _parse_extractor_response
```

In `tests/test_tool_curator.py`:
```python
# old
from tool_curator import (
# new
from pipeline.tool_curator import (
```
Also update:
```python
# old
from workflow_groups import WORKFLOW_GROUPS
# new
from pipeline.workflow_groups import WORKFLOW_GROUPS
```

In `tests/test_workflow_groups.py`:
```python
# old
from workflow_groups import WORKFLOW_GROUPS, WorkflowGroup
# new
from pipeline.workflow_groups import WORKFLOW_GROUPS, WorkflowGroup
```

- [30 pass, 1 fail, need rewrite of www_cookies] **Step 7: Run tests to verify**

```bash
uv run pytest tests/test_task_extractor.py tests/test_tool_curator.py tests/test_workflow_groups.py -v
```
Expected: All pass with no import errors.

- [✓] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: move pipeline modules into pipeline/ package"
```

---

### Task 3: Move Remaining Root Files

**Files:**
- Move: `credentials.py` → `auth/credentials.py`
- Move: `client_agent.py` → `atomic_client/agent.py`
- Move: `client_bridge.py` → `atomic_client/bridge.py`
- Create: `atomic_client/__init__.py`

- [✓] **Step 1: Move credentials**

```bash
git mv credentials.py auth/credentials.py
```

Check for imports:
```bash
grep -r "from credentials" --include="*.py" .
grep -r "import credentials" --include="*.py" .
```
Update any found imports from `credentials` to `auth.credentials`.

- [✓] **Step 2: Create atomic_client and move stubs**

```bash
mkdir -p atomic_client
git mv client_agent.py atomic_client/agent.py
git mv client_bridge.py atomic_client/bridge.py
```

Create `atomic_client/__init__.py`:
```python
"""Atomic client — stubs for future replacement."""
```

- [ ] **Step 3: Verify clean root**

```bash
ls *.py *.md *.sh *.toml *.lock
```
Expected: `main.py`, `tools_server.py`, `config.py`, `context.py`, `CLAUDE.md`, `start.sh`, `pyproject.toml`, `uv.lock` — nothing else.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: move credentials to auth/, client stubs to atomic_client/"
```

---

### Task 4: Refactor `tools/accounting.py` — Kill Aliases and Merge FIFO/LIFO

**Files:**
- Modify: `tools/accounting.py`
- Modify: `pipeline/workflow_groups.py` — update `fa_tx_fifo`/`fa_tx_lifo` → `fa_tx_sale`
- Modify: `tests/test_accounting_primitives.py` — if it tests aliases
- Modify: `tests/test_accounting_fifo_lifo.py` — update tool name

- [ ] **Step 1: Delete the 10 alias functions and dispatch table**

Delete these lines (approximately lines 122-167):
```python
# DELETE all of these:
def _debit_asset(db, entry, account, amount, memo=None):
    return _debit_account(db, entry, account, amount, memo)

def _credit_asset(db, entry, account, amount, memo=None):
    return _credit_account(db, entry, account, amount, memo)

def _debit_liability(db, entry, account, amount, memo=None):
    return _debit_account(db, entry, account, amount, memo)

def _credit_liability(db, entry, account, amount, memo=None):
    return _credit_account(db, entry, account, amount, memo)

def _debit_equity(db, entry, account, amount, memo=None):
    return _debit_account(db, entry, account, amount, memo)

def _credit_equity(db, entry, account, amount, memo=None):
    return _credit_account(db, entry, account, amount, memo)

def _debit_revenue(db, entry, account, amount, memo=None):
    return _debit_account(db, entry, account, amount, memo)

def _credit_revenue(db, entry, account, amount, memo=None):
    return _credit_account(db, entry, account, amount, memo)

def _debit_expense(db, entry, account, amount, memo=None):
    return _debit_account(db, entry, account, amount, memo)

def _credit_expense(db, entry, account, amount, memo=None):
    return _credit_account(db, entry, account, amount, memo)

_PRIMITIVE_DISPATCH = {
    (AccountType.ASSET, "debit"): _debit_asset,
    ...
}
```

- [ ] **Step 2: Replace dispatch call in `_journalize_transaction_impl`**

In `_journalize_transaction_impl`, replace the dispatch lookup (around line 558):
```python
# old
primitive = _PRIMITIVE_DISPATCH[(account.account_type, side)]
jl = primitive(db, entry, account, amount, line_memo)

# new
if side == "debit":
    jl = _debit_account(db, entry, account, amount, line_memo)
else:
    jl = _credit_account(db, entry, account, amount, line_memo)
```

- [ ] **Step 3: Delete FIFO/LIFO wrapper functions**

Delete `_journalize_fifo_transaction_impl` and `_journalize_lifo_transaction_impl` (around lines 1216-1274). They are one-line wrappers around `_journalize_cost_layer_sale`.

- [ ] **Step 4: Merge `fa_tx_fifo` + `fa_tx_lifo` → `fa_tx_sale`**

Delete both `JournalizeFifoTransactionTool` and `JournalizeLifoTransactionTool` classes. Replace with:

```python
@register_tool('fa_tx_sale')
class JournalizeCostLayerSaleTool(BaseTool):
    description = 'Record an inventory sale using FIFO or LIFO costing.'
    parameters = {
        'type': 'object',
        'properties': {
            'date': {'type': 'string', 'description': 'Sale date (YYYY-MM-DD).'},
            'memo': {'type': 'string', 'description': 'Transaction description.'},
            'item_sku': {'type': 'string', 'description': 'SKU of the item being sold.'},
            'quantity': {'type': 'number', 'description': 'Units sold.'},
            'method': {'type': 'string', 'description': '"fifo" or "lifo". Default: "fifo".'},
            'sale_price_per_unit': {'type': 'number', 'description': 'Price per unit. Omit for internal consumption.'},
            'revenue_account': {'type': 'string', 'description': 'Revenue account name. Default: "Revenue".'},
            'receivable_account': {'type': 'string', 'description': 'Account to debit. Default: "Cash".'},
        },
        'required': ['date', 'memo', 'item_sku', 'quantity'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        from flask_login import current_user
        p = json5.loads(params)
        db = _get_db()
        try:
            result = _journalize_cost_layer_sale(
                db, current_user.id,
                p['date'], p['memo'], p['item_sku'], p['quantity'],
                p.get('sale_price_per_unit'),
                p.get('revenue_account', 'Revenue'),
                p.get('receivable_account', 'Cash'),
                method=p.get('method', 'fifo'),
            )
            db.commit()
            return result
        except Exception as e:
            db.rollback()
            return tool_result(error=str(e))
        finally:
            db.close()
```

- [ ] **Step 5: Update `pipeline/workflow_groups.py`**

```python
# old (in Accounting group tools list)
"fa_tx_fifo", "fa_tx_lifo",
# new
"fa_tx_sale",
```

```python
# old (in TOOL_REF)
"fa_tx_fifo":          "FIFO sale",
"fa_tx_lifo":          "LIFO sale",
# new
"fa_tx_sale":          "inventory sale (FIFO/LIFO)",
```

- [ ] **Step 6: Update tests**

In `tests/test_accounting_fifo_lifo.py`, replace any references to `fa_tx_fifo` / `fa_tx_lifo` tool names with `fa_tx_sale`, adding `method` param.

- [ ] **Step 7: Run accounting tests**

```bash
uv run pytest tests/test_accounting_primitives.py tests/test_accounting_fifo_lifo.py tests/test_accounting_journal.py -v
```
Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add tools/accounting.py pipeline/workflow_groups.py tests/
git commit -m "refactor: kill aliases and merge FIFO/LIFO into fa_tx_sale"
```

---

### Task 5: Refactor `tools/ecommerce.py` — Kill Dispatchers, Merge Tools

**Files:**
- Modify: `tools/ecommerce.py`
- Modify: `pipeline/workflow_groups.py`
- Modify: `tests/test_tools_ecommerce.py`

- [ ] **Step 1: Extract shared helpers**

Add at the top of the file, after imports:

```python
def _validate_query(query: str) -> str | None:
    """Return error string if query is invalid, None if ok."""
    if not query.strip():
        return "query must be a non-empty string"
    return None


def _ebay_url(query: str, sort: str = "best_match", min_price=None, max_price=None,
              condition: str = "", sold: bool = False, page: int = 1) -> str:
    """Build an eBay search URL."""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.ebay.com/sch/i.html?_nkw={encoded}"
    url += EBAY_SORT_OPTIONS.get(sort, "")
    if min_price is not None:
        url += f"&_udlo={min_price}"
    if max_price is not None:
        url += f"&_udhi={max_price}"
    condition_map = {
        "new": "&LH_ItemCondition=1000",
        "used": "&LH_ItemCondition=3000",
        "refurbished": "&LH_ItemCondition=2500",
        "parts": "&LH_ItemCondition=7000",
    }
    if condition.lower() in condition_map:
        url += condition_map[condition.lower()]
    if sold:
        url += "&LH_Complete=1&LH_Sold=1"
    else:
        url += "&LH_BIN=1"
    url += "&rt=nc"
    if page > 1:
        url += f"&_pgn={page}"
    return url


_EBAY_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"}


def _fetch_html(url: str, headers: dict = None) -> str:
    """Fetch a URL and return decoded HTML. Raises on failure."""
    req = urllib.request.Request(url, headers=headers or _EBAY_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")
```

- [ ] **Step 2: Merge eBay tools into one `ebay_search`**

Delete `EbaySearchTool`, `EbaySoldSearchTool`, `EbayDeepScanTool`. Replace with:

```python
@register_tool('ebay_search')
class EbaySearchTool(BaseTool):
    description = 'Search eBay listings by keyword with optional filters.'
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search terms.'},
            'sort': {'type': 'string', 'description': 'Sort: best_match, ending_soonest, newly_listed, price_low, price_high.'},
            'min_price': {'type': 'number', 'description': 'Minimum price USD.'},
            'max_price': {'type': 'number', 'description': 'Maximum price USD.'},
            'condition': {'type': 'string', 'description': 'new, used, refurbished, or parts.'},
            'sold': {'type': 'boolean', 'description': 'Search completed/sold listings instead of active. Default: false.'},
            'pages': {'type': 'integer', 'description': 'Pages to scrape (1-10). Default: 1.'},
            'max_results': {'type': 'integer', 'description': 'Max listings to return. Default: 20.'},
        },
        'required': ['query'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        query = p.get('query', '')
        err = _validate_query(query)
        if err:
            return tool_result(error=err)

        sort = p.get('sort', 'best_match')
        min_price = p.get('min_price')
        max_price = p.get('max_price')
        condition = p.get('condition', '')
        sold = p.get('sold', False)
        pages = max(1, min(p.get('pages', 1), 10))
        max_results = p.get('max_results', 20)

        seen_urls = set()
        all_listings = []

        for page_num in range(1, pages + 1):
            url = _ebay_url(query, sort, min_price, max_price, condition, sold, page_num)
            try:
                html = _fetch_html(url)
            except Exception:
                if page_num < pages:
                    time.sleep(random.uniform(3.0, 6.0))
                continue

            for listing in _parse_ebay_listings(html):
                item_url = listing.get("url", "")
                if not item_url or item_url in seen_urls:
                    continue
                seen_urls.add(item_url)
                if sold:
                    listing["sold"] = True
                all_listings.append(listing)

            if page_num < pages:
                time.sleep(random.uniform(3.0, 6.0))

        all_listings = all_listings[:max_results]
        return tool_result(data={"query": query, "count": len(all_listings), "listings": all_listings})
```

- [ ] **Step 3: Merge Craigslist tools into one `cl_search`**

Delete `CraigslistSearchTool` and `CraigslistMultiSearchTool`. Replace with:

```python
@register_tool('cl_search')
class CraigslistSearchTool(BaseTool):
    description = 'Search Craigslist in one city or across multiple cities.'
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search terms.'},
            'city': {'type': 'string', 'description': 'Single city name. Ignored if scope is set.'},
            'scope': {'type': 'string', 'description': 'Search multiple cities: "local" (Denver area), "shipping" (20 cities), or "all". Overrides city.'},
            'category': {'type': 'string', 'description': 'Category: sss (for sale), cta (cars), sys (computers), ele (electronics). Default: sss.'},
            'min_price': {'type': 'integer', 'description': 'Minimum price USD.'},
            'max_price': {'type': 'integer', 'description': 'Maximum price USD.'},
            'max_results': {'type': 'integer', 'description': 'Max listings per city. Default: 25.'},
        },
        'required': ['query'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        query = p.get('query', '')
        err = _validate_query(query)
        if err:
            return tool_result(error=err)

        scope = p.get('scope')
        city = p.get('city', 'denver')
        category = p.get('category', 'sss')
        min_price = p.get('min_price')
        max_price = p.get('max_price')
        max_results = p.get('max_results', 25)

        # Build city list
        if scope:
            cities = []
            if scope in ("local", "all"):
                cities += [(n, u, True) for n, u in CRAIGSLIST_DENVER_AREA.items()]
            if scope in ("shipping", "all"):
                cities += [(n, u, False) for n, u in CRAIGSLIST_SHIPPING_CITIES.items()]
            if not cities:
                return tool_result(error=f"Invalid scope '{scope}'. Use 'local', 'shipping', or 'all'.")
        else:
            city_lower = city.lower().strip()
            if city_lower in CRAIGSLIST_DENVER_AREA:
                cities = [(city_lower, CRAIGSLIST_DENVER_AREA[city_lower], True)]
            elif city_lower in CRAIGSLIST_SHIPPING_CITIES:
                cities = [(city_lower, CRAIGSLIST_SHIPPING_CITIES[city_lower], False)]
            else:
                all_cities = sorted(list(CRAIGSLIST_DENVER_AREA) + list(CRAIGSLIST_SHIPPING_CITIES))
                return tool_result(error=f"Unknown city '{city}'. Use one of: {', '.join(all_cities)}")

        all_listings = []
        for i, (name, base_url, is_local) in enumerate(cities):
            results = _craigslist_search_city(
                base_url, query, name, is_local,
                category=category, min_price=min_price, max_price=max_price,
                max_results=max_results,
            )
            all_listings.extend(results)
            if i < len(cities) - 1:
                time.sleep(random.uniform(1.5, 3.0))

        return tool_result(data={"query": query, "count": len(all_listings), "listings": all_listings})
```

- [ ] **Step 4: Delete dispatcher and cross-platform tools**

Delete these classes entirely:
- `CrossPlatformSearchTool`
- `DealFinderTool`
- `EcommerceSearchTool` (the `ec_search` dispatcher)
- The `_EC_SEARCH_HANDLERS` dict

Keep `AmazonSearchTool` as-is but register it: add `@register_tool('amazon_search')` decorator.

Keep `EnrichmentPipelineTool` as-is (it's standalone, not a dispatcher).

- [ ] **Step 5: Update `pipeline/workflow_groups.py`**

```python
# old
"Ecommerce": WorkflowGroup(
    tools=["ec_search", "ec_deals", "ec_enrich"],
    tooltip="Product search across eBay, Amazon, and Craigslist",
),

# new
"Ecommerce": WorkflowGroup(
    tools=["ebay_search", "amazon_search", "cl_search", "ec_enrich"],
    tooltip="Product search across eBay, Amazon, and Craigslist",
),
```

Update TOOL_REF:
```python
# old
"ec_search":           "search listings",
"ec_deals":            "find deals",

# new
"ebay_search":         "search eBay listings",
"amazon_search":       "search Amazon listings",
"cl_search":           "search Craigslist",
```

- [ ] **Step 6: Update tests**

In `tests/test_tools_ecommerce.py`, update any references to old tool names (`ec_search`, `ec_deals`) to the new names (`ebay_search`, `amazon_search`, `cl_search`).

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/test_tools_ecommerce.py tests/test_workflow_groups.py -v
```
Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add tools/ecommerce.py pipeline/workflow_groups.py tests/
git commit -m "refactor: merge eBay/CL tools, kill ec_search dispatcher"
```

---

### Task 6: Refactor `tools/onlyfans.py` — Merge Save Tools

**Files:**
- Modify: `tools/onlyfans.py`
- Modify: `pipeline/workflow_groups.py`

- [ ] **Step 1: Merge `of_save_img` + `of_save_vid` → `of_save_media`**

Delete `SaveImageTool` and `SaveVideoTool`. Replace with:

```python
@register_tool('of_save_media')
class SaveMediaTool(BaseTool):
    description = 'Download and save a media file from a URL to disk.'
    parameters = {
        'type': 'object',
        'properties': {
            'url': {'type': 'string', 'description': 'Direct media URL.'},
            'file_path': {'type': 'string', 'description': 'Local path to save to.'},
        },
        'required': ['url', 'file_path'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        url = p['url']
        file_path = p['file_path']
        if not url.startswith(("http://", "https://")):
            return tool_result(error="url must start with http:// or https://")
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            with open(file_path, "wb") as f:
                f.write(r.content)
            return tool_result(data={"url": url, "file_path": file_path, "bytes": len(r.content)})
        except Exception as e:
            return tool_result(error=str(e))
```

- [ ] **Step 2: Update internal references**

In `ExtractImagesAndVideosTool.call()`, replace:
```python
# old
save_image_tool = SaveImageTool()
save_video_tool = SaveVideoTool()
...
save_image_tool.call(json5.dumps({...}))
...
save_video_tool.call(json5.dumps({...}))

# new
save_tool = SaveMediaTool()
...
save_tool.call(json5.dumps({...}))
...
save_tool.call(json5.dumps({...}))
```

- [ ] **Step 3: Update `pipeline/workflow_groups.py`**

```python
# old
"of_save_img", "of_save_vid"
# new
"of_save_media"
```

TOOL_REF:
```python
# old
"of_save_img":         "save image",
"of_save_vid":         "save video",
# new
"of_save_media":       "save media file",
```

- [ ] **Step 4: Commit**

```bash
git add tools/onlyfans.py pipeline/workflow_groups.py
git commit -m "refactor: merge of_save_img/of_save_vid into of_save_media"
```

---

### Task 7: Fix `tools/web.py` — Broken Cookie Tool, Extract Validators

**Files:**
- Modify: `tools/web.py`

- [ ] **Step 1: Fix `www_cookies` parameter schema**

Replace the broken `parameters` dict:
```python
# old (broken — uses Python type/object instead of JSON schema strings)
parameters = {
    'cookies': {
        "type": object
    },
    'domain': {
        type: str
    }
}

# new
parameters = {
    'type': 'object',
    'properties': {
        'cookies': {'type': 'string', 'description': 'Semicolon-separated cookies in "name=value" format.'},
        'domain': {'type': 'string', 'description': 'Cookie domain (e.g. ".example.com").'},
    },
    'required': ['cookies', 'domain'],
}
```

- [ ] **Step 2: Fix `www_cookies` call() method**

The current `call()` references undefined `dot_domain` and has broken cookie parsing. Rewrite:

```python
@retry()
def call(self, params: str, **kwargs) -> dict:
    p = json5.loads(params)
    cookies_str = p.get('cookies', '').strip()
    domain = p.get('domain', '').strip()

    if not cookies_str:
        return tool_result(error="cookies is required")
    if not domain:
        return tool_result(error="domain is required")

    dot_domain = domain if domain.startswith(".") else "." + domain

    parsed = []
    for pair in cookies_str.split(";"):
        pair = pair.strip()
        if "=" in pair:
            name, _, value = pair.partition("=")
            parsed.append({"name": name.strip(), "value": value.strip()})

    if not parsed:
        return tool_result(error="No valid name=value cookie pairs found")

    _apply_cookies("https://" + domain.lstrip("."), [f"{c['name']}={c['value']}" for c in parsed], dot_domain)

    if _browser_driver is not None:
        try:
            driver = _browser_driver
            driver.get(f"https://{domain.lstrip('.')}")
            time.sleep(1)
            for c in parsed:
                driver.add_cookie({"name": c["name"], "value": c["value"], "domain": dot_domain})
        except Exception:
            pass

    return tool_result(data={
        "domain": dot_domain,
        "cookies_set": len(parsed),
        "names": [c["name"] for c in parsed],
    })
```

- [ ] **Step 3: Extract `_validate_url` helper**

Add near the top of `web.py`:

```python
def _validate_url(url: str) -> str | None:
    """Return error string if URL is invalid, None if ok."""
    if not url.startswith(("http://", "https://")):
        return "url must start with http:// or https://"
    return None
```

Replace all instances of `if not url or not url.startswith(("http://", "https://"))` with:
```python
err = _validate_url(url)
if err:
    return tool_result(error=err)
```

This applies in: `FetchUrlTool`, `WebscrapeTool`, `FindDownloadLinkTool`, `FindAllowedRoutesTool`, `BrowserFetchTool`.

- [ ] **Step 4: Run web tests**

```bash
uv run pytest tests/test_tools_web.py -v
```
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add tools/web.py
git commit -m "fix: repair www_cookies tool, extract URL validator"
```

---

### Task 8: Consolidate Pipeline — `process_message()` Entry Point

**Files:**
- Modify: `pipeline/__init__.py`
- Modify: `main.py` — replace inline pipeline code with single call

- [ ] **Step 1: Write `pipeline/__init__.py` with `process_message()`**

```python
"""Recommendation pipeline — message classification, task extraction, tool curation.

Single entry point: process_message() classifies, extracts tasks, curates tools,
and returns the function_list for the qwen-agent Assistant.
"""

import logging

from qwen_agent.tools.base import TOOL_REGISTRY as QW_TOOL_REGISTRY

from pipeline.gate import _gate_classify
from pipeline.workflow_groups import WORKFLOW_GROUPS, tools_for_groups, group_for_tool

logger = logging.getLogger(__name__)

_ALWAYS_TOOLS = {"get_params", "list_tools", "mark_task_done", "unmark_task_done", "mcp_connect"}
_BUILTIN_TOOL_NAMES = set()  # populated by main.py at import time


def set_builtin_tools(names: set[str]):
    """Called once from main.py after qwen-agent builtins are captured."""
    global _BUILTIN_TOOL_NAMES
    _BUILTIN_TOOL_NAMES = names


def process_message(
    user_message: str,
    conversation_id: str,
    user_tool_names: list[str],
    db,
) -> dict:
    """Run the full pipeline. Returns dict with keys:
        - classification: str
        - function_list: list[str]
        - task_list: list[dict]
    """
    from auth.conversation_tasks import ConversationTask
    from auth.conversations import ConversationMessage

    # Load context for gate
    recent = (
        db.query(ConversationMessage)
        .filter_by(conversation_id=conversation_id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(10)
        .all()
    )
    recent_messages = [{"role": m.role, "content": m.content} for m in reversed(recent)]

    # Step 1: Classify
    classification = _gate_classify(user_message, recent_messages)
    logger.info("pipeline GATE: %s", classification)

    if classification == "conversational":
        function_list = [n for n in _ALWAYS_TOOLS if n in QW_TOOL_REGISTRY]
        return {"classification": classification, "function_list": function_list, "task_list": []}

    # Step 2: For tool_required/mixed, give the agent all user-selected tools
    user_set = set(user_tool_names)
    function_list = [n for n in user_set if n in QW_TOOL_REGISTRY and n not in _BUILTIN_TOOL_NAMES]

    # Always include internal tools
    for t in _ALWAYS_TOOLS:
        if t in QW_TOOL_REGISTRY and t not in function_list:
            function_list.append(t)

    logger.info("pipeline: %d tools for agent", len(function_list))

    return {
        "classification": classification,
        "function_list": function_list,
        "task_list": [],
    }
```

Note: This intentionally simplifies the pipeline. The task extractor, tool curator, and recommendation pause/resume are removed for now. The agent gets the user's selected tools directly. This can be layered back in once the basics work.

- [ ] **Step 2: Simplify `main.py` `chat_stream` generator**

Replace the entire `generate()` function's tool-selection block (lines ~459-534) with:

```python
from pipeline import process_message, set_builtin_tools

# (at module level, after _BUILTIN_TOOL_NAMES is set)
set_builtin_tools(_BUILTIN_TOOL_NAMES)
```

Inside `generate()`, replace the classification/tool routing block with:

```python
result = process_message(user_msg, conversation_id, user_tool_names, db)
classification = result["classification"]
function_list = result["function_list"]
```

Delete the `analyze_message` call, the inline group mapping, and the recommendation event/wait block. The `_recommendation_events` and `_recommendation_responses` dicts can stay (they'll be unused but harmless) or be deleted.

- [ ] **Step 3: Remove old imports from `main.py`**

```python
# delete
from pipeline.gate import analyze_message
```

Add:
```python
from pipeline import process_message, set_builtin_tools
```

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest -v
```
Expected: All pass. Some tests may need import updates.

- [ ] **Step 5: Commit**

```bash
git add pipeline/__init__.py main.py
git commit -m "refactor: consolidate pipeline into process_message() entry point"
```

---

### Task 9: Rewrite System Prompt

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Replace `_SYSTEM_BASE`**

Replace the entire `_SYSTEM_BASE` string (lines ~40-65) with:

```python
_SYSTEM_BASE = """You are a helpful, friendly assistant with access to tools. You're great at conversation, explanation, and reasoning — and when a task needs it, you can call tools to get things done.

AVAILABLE TOOLS:
{tool_ref}

TOOL RULES:
- Call get_params(tool_name) before calling any tool to learn its parameters.
- Only call tools listed above. Never invent tool names.
- Use real values from the user message — never use placeholders like "example.com" or "your_query_here".
- If a tool returns the same error twice, stop retrying and tell the user what happened.
- Copy strings from the user message exactly. Preserve hyphens, dots, spaces, and special characters.
"""
```

- [ ] **Step 2: Verify the format string still works**

Search for `_SYSTEM_BASE.format(tool_ref=` in `main.py` — there should be two call sites (one in `generate()`, one in `cli_chat()`). Confirm both still pass `tool_ref=tool_ref_text`.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "fix: rewrite system prompt — conversational first, tool-capable second"
```

---

### Task 10: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the backend layout section**

Replace the backend layout section to reflect the new structure:

```markdown
## Backend layout

- `main.py` — Flask app, `/api/chat/stream` NDJSON endpoint, qwen-agent `Assistant.run()` loop
- `config.py` — env-driven constants; `qwen_llm_cfg()` / `qwen_curation_llm_cfg()` build qwen-agent LLM dicts
- `context.py` — converts DB message rows to qwen-agent message dicts
- `tools_server.py` — outbound MCP tool server
- `pipeline/` — recommendation pipeline
  - `__init__.py` — `process_message()` entry point (classify → build function_list)
  - `gate.py` — 1.7B worker: classifies messages as conversational/tool_required/mixed
  - `task_extractor.py` — 1.7B worker: extracts tasks from messages → `conversation_tasks` table
  - `tool_curator.py` — 1.7B worker: maps tasks to tools and recommends workflow groups
  - `workflow_groups.py` — static registry mapping group names to tool lists
- `auth/` — SQLAlchemy models + DB setup, credentials, routes, middleware
- `tools/` — tool implementations as qwen-agent `@register_tool` + `BaseTool` classes
- `routes/` — Flask blueprints
- `atomic_client/` — client stubs (future replacement)
```

- [ ] **Step 2: Update context-specific reading guides**

Update "Working on the chat pipeline" to reference `pipeline/` paths instead of root-level files.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for new project structure"
```

---

### Task 11: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest -v
```
Expected: All pass.

- [ ] **Step 2: Verify root directory is clean**

```bash
ls *.py *.md *.sh *.toml *.lock 2>/dev/null
```
Expected: `main.py config.py context.py tools_server.py CLAUDE.md start.sh pyproject.toml uv.lock`

- [ ] **Step 3: Verify app starts**

```bash
uv run python -c "import main; print('OK')"
```
Expected: `OK`, no import errors.

- [ ] **Step 4: Check line counts improved**

```bash
wc -l tools/*.py pipeline/*.py main.py
```
Compare against original counts: `accounting.py` 1805→~1200, `ecommerce.py` 1270→~900, `onlyfans.py` 290→~220.

- [ ] **Step 5: Final commit if any loose changes**

```bash
git status
```
If clean, done. If stragglers, commit them.
