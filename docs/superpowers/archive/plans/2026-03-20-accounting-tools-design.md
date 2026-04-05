# Accounting Tools Module — Design Spec

**Date:** 2026-03-20
**Goal:** Add a full double-entry accounting system as LLM-facing tools, backed by the existing PostgreSQL database. Each user who opts in gets an isolated ledger.

---

## Architecture

New file: `tools/accounting.py` — 21 LLM-facing tools + 10 internal primitives.
New file: `agents/accounting.py` — MCP agent server (follows existing pattern).
New migration: adds 6 tables to the existing PostgreSQL database.

All tools return standardized JSON: `{"status": "success"|"error", "data": ..., "error": ""}` via `tools/_output.py:tool_result()`.

User isolation: every table is keyed by `ledger_id`, and every ledger belongs to exactly one `user_id`. Tools resolve the current user's ledger automatically.

---

## Database Schema

### `ledgers`

| Column | Type | Notes |
|--------|------|-------|
| `id` | serial PK | |
| `user_id` | FK → users | unique — one ledger per user |
| `name` | varchar(255) | e.g. "Personal", "My Business" |
| `currency` | varchar(3) | default 'USD' — stored for future multi-currency support |
| `created_at` | timestamptz | default now() |

### `accounts`

| Column | Type | Notes |
|--------|------|-------|
| `id` | serial PK | |
| `ledger_id` | FK → ledgers | |
| `account_type` | enum | asset, liability, equity, revenue, expense |
| `name` | varchar(255) | |
| `account_number` | varchar(20) | optional, user-assigned |
| `parent_id` | FK → accounts | nullable, for sub-accounts |
| `normal_balance` | enum | debit, credit — derived from type, stored for query speed |
| `is_active` | boolean | default true |
| `created_at` | timestamptz | default now() |

Unique constraints: `(ledger_id, name)`, `(ledger_id, account_number) WHERE account_number IS NOT NULL`.

### `journal_entries`

| Column | Type | Notes |
|--------|------|-------|
| `id` | serial PK | |
| `ledger_id` | FK → ledgers | |
| `date` | date | transaction date |
| `memo` | text | |
| `is_void` | boolean | default false |
| `void_of_id` | FK → journal_entries | nullable — points to original if this is a reversal |
| `source_type` | enum | manual, fifo_sale, lifo_sale, inventory_receipt, period_close, void — identifies how this entry was created |
| `created_at` | timestamptz | default now() |

### `journal_lines`

| Column | Type | Notes |
|--------|------|-------|
| `id` | serial PK | |
| `journal_entry_id` | FK → journal_entries | |
| `account_id` | FK → accounts | |
| `debit` | decimal(15,2) | default 0 |
| `credit` | decimal(15,2) | default 0 |
| `memo` | text | nullable — per-line description (e.g. cost layer details on FIFO entries) |

Constraint: `CHECK (debit >= 0 AND credit >= 0 AND (debit > 0) != (credit > 0))` — each line is one side only, never both, never zero.

### `inventory_items`

| Column | Type | Notes |
|--------|------|-------|
| `id` | serial PK | |
| `ledger_id` | FK → ledgers | |
| `item_type` | enum | goods, service |
| `sku` | varchar(100) | |
| `description` | text | |
| `default_sale_price` | decimal(15,2) | nullable |
| `is_active` | boolean | default true |
| `created_at` | timestamptz | default now() |

Unique constraint: `(ledger_id, sku)`.

### `inventory_layers`

| Column | Type | Notes |
|--------|------|-------|
| `id` | serial PK | |
| `item_id` | FK → inventory_items | |
| `journal_entry_id` | FK → journal_entries | links layer to the purchase entry that created it |
| `quantity_purchased` | decimal(15,4) | original quantity |
| `quantity_remaining` | decimal(15,4) | decremented on sale/usage |
| `unit_cost` | decimal(15,4) | |
| `received_date` | date | |
| `created_at` | timestamptz | default now() |

---

## Double-Entry Rules Engine

Every account type has a normal balance that determines the effect of debits and credits:

| Account Type | Normal Balance | Debit Effect | Credit Effect |
|---|---|---|---|
| Asset | Debit | **Increase** | Decrease |
| Expense | Debit | **Increase** | Decrease |
| Liability | Credit | Decrease | **Increase** |
| Equity | Credit | Decrease | **Increase** |
| Revenue | Credit | Decrease | **Increase** |

### Internal Primitives (not @tool, not LLM-facing)

```
_debit_asset(account, amount)      → increases asset balance
_credit_asset(account, amount)     → decreases asset balance
_debit_liability(account, amount)  → decreases liability balance
_credit_liability(account, amount) → increases liability balance
_debit_equity(account, amount)     → decreases equity
_credit_equity(account, amount)    → increases equity
_debit_revenue(account, amount)    → decreases revenue (reversal)
_credit_revenue(account, amount)   → increases revenue (sale)
_debit_expense(account, amount)    → increases expense
_credit_expense(account, amount)   → decreases expense (reversal)
```

These are dispatched automatically by `journalize_transaction` based on the account's `account_type` field. The LLM specifies which side (debit/credit) — the account type determines the effect.

### Validation Rules

`journalize_transaction` enforces before committing:

1. Sum of debits must equal sum of credits — rejects otherwise, no partial writes
2. Each line targets a real, active account in the user's ledger
3. Amount must be positive — the primitive determines direction, never a negative number
4. Account type determines which primitive is called — you cannot debit an asset using a liability primitive

---

## Tool Definitions (21 LLM-facing)

### Ledger Setup (2)

**`create_ledger`**
- Initializes a ledger for the current user
- Creates default accounts (these are the **canonical names** referenced by automated tools):
  - **Assets:** Cash, Accounts Receivable, Inventory
  - **Liabilities:** Accounts Payable
  - **Equity:** Owner's Capital, Income Summary
  - **Revenue:** Revenue
  - **Expenses:** Cost of Goods Sold, Rent Expense, Utilities Expense, Supplies Expense, Wages Expense
- Returns: ledger id, list of default accounts created
- Error if user already has a ledger

**Canonical account names:** FIFO/LIFO tools use exact names "Inventory", "Cost of Goods Sold", "Revenue", and "Cash" for auto-generated journal lines. The `receive_inventory` tool uses "Inventory" as the debit account. Users can create additional accounts but must not rename or deactivate canonical accounts while inventory tools depend on them.

**`create_account`**
- Args: `name` (str), `account_type` (asset/liability/equity/revenue/expense), `account_number` (optional str), `parent_id` (optional int)
- Validates: name unique within ledger, valid type, parent exists if specified
- `normal_balance` is derived from `account_type` automatically

### Journal Entry (3)

**`journalize_transaction`**
- Args: `date` (str, YYYY-MM-DD), `memo` (str), `lines` (array of `{"account": str, "debit": float, "credit": float}`)
- Validates: debits == credits, all accounts exist and are active, amounts positive, each line has debit XOR credit
- Resolves account types, calls appropriate internal primitives
- Commits atomically in a single DB transaction
- Returns: journal entry id, line details with account types and effects

**`journalize_fifo_transaction`**
- Args: `date` (str), `memo` (str), `item_sku` (str), `quantity` (float), `sale_price_per_unit` (optional float — null for internal usage/consumption), `revenue_account` (optional str, default "Revenue"), `receivable_account` (optional str, default "Cash")
- Rejects if item is `item_type = 'service'` (services have no cost layers)
- Rejects if total `quantity_remaining` across all layers < requested quantity (no partial fulfillment, no negative inventory)
- Pulls cost layers oldest-first, decrements `quantity_remaining`
- Auto-generates journal lines using canonical account names: Debit "Cost of Goods Sold" + Credit "Inventory" (at cost). If sale: Debit receivable_account + Credit revenue_account (at sale price).
- Per-line memo on each COGS line identifies which cost layer was consumed
- Returns: journal entry id, cost layers consumed, total COGS, sale total

**`journalize_lifo_transaction`**
- Same as FIFO but pulls newest cost layers first
- Same rejection rules: no services, no insufficient inventory

### Inventory (3)

**`register_inventory_item`**
- Args: `sku` (str), `description` (str), `item_type` ("goods"/"service"), `default_sale_price` (optional float)
- Validates: SKU unique within ledger

**`receive_inventory`**
- Args: `item_sku` (str), `quantity` (float), `unit_cost` (float), `date` (str), `payment_account` (str — e.g. "Cash" or "Accounts Payable")
- Creates a cost layer in `inventory_layers`
- Auto-journals: debit Inventory, credit payment_account
- Returns: journal entry id, new layer details

**`list_inventory_items`**
- Args: none (operates on current user's ledger)
- Returns: all items with SKU, description, type, total quantity on hand, number of cost layers

### Period Close (1)

**`close_period`**
- Args: `period_end_date` (str, YYYY-MM-DD)
- Executes 3 steps atomically:
  1. Close revenue: **Debit** each revenue account (zeroing it), **Credit** Income Summary for the total
  2. Close expenses: **Credit** each expense account (zeroing it), **Debit** Income Summary for the total
  3. Close Income Summary: if net income (credit balance) → **Debit** Income Summary, **Credit** Owner's Capital. If net loss (debit balance) → **Credit** Income Summary, **Debit** Owner's Capital.
- Creates Income Summary as a temporary equity account if it doesn't exist
- Skips accounts with zero balances (avoids zero-amount lines that violate the journal_lines CHECK constraint)
- If all revenue and expense accounts are zero, returns early with a "nothing to close" message — no journal entries created
- Returns: net income/loss amount, journal entry IDs (up to 3, fewer if steps were skipped)

### Reporting (6)

**`trial_balance`**
- Args: `as_of_date` (optional str, defaults to today)
- Returns: all accounts with debit total, credit total, net balance
- Includes a total row — debits and credits must be equal

**`income_statement`**
- Args: `start_date` (str), `end_date` (str)
- Returns: revenue accounts with totals, expense accounts with totals, net income/loss

**`balance_sheet`**
- Args: `as_of_date` (optional str, defaults to today)
- Returns: assets (with subtotal), liabilities (with subtotal), equity (with subtotal)
- Validates: assets == liabilities + equity

**`cash_flow_statement`**
- Args: `start_date` (str), `end_date` (str)
- Uses indirect method: starts from net income, adjusts for non-cash items and working capital changes
- Returns: operating activities, investing activities, financing activities, net change in cash, beginning cash, ending cash
- Operating: net income +/- changes in AR, AP, inventory, depreciation
- Investing: changes in long-term asset accounts
- Financing: changes in long-term liability and equity accounts (excluding retained earnings/net income)

**`account_ledger`**
- Args: `account_name` (str), `start_date` (optional str), `end_date` (optional str)
- Returns: all journal lines for this account with running balance, entry date, memo

**`inventory_valuation`**
- Args: `method` ("fifo"/"lifo", default "fifo")
- Returns: per-item valuation with quantity on hand, total cost, weighted average unit cost

### Utilities (6)

**`list_accounts`**
- Args: `account_type` (optional str — filter by type)
- Returns: chart of accounts with id, name, type, number, balance, active status

**`get_account_balance`**
- Args: `account_name` (str), `as_of_date` (optional str)
- Returns: single account's current balance, normal balance side, account type
- Lightweight alternative to pulling full trial_balance

**`update_account`**
- Args: `account_name` (str), `new_name` (optional str), `new_account_number` (optional str), `is_active` (optional bool)
- Validates: new name unique if changed, cannot deactivate canonical accounts with non-zero balances
- Returns: updated account details

**`deactivate_inventory_item`**
- Args: `item_sku` (str)
- Sets `is_active = false`
- Rejects if `quantity_remaining > 0` on any layer (must be depleted first)
- Returns: confirmation with item details

**`search_journal`**
- Args: `start_date` (optional), `end_date` (optional), `memo_text` (optional), `min_amount` (optional), `max_amount` (optional), `account_name` (optional)
- Returns: matching journal entries with all lines

**`void_transaction`**
- Args: `journal_entry_id` (int), `date` (str), `memo` (str)
- **Rejects** if the entry is already voided (`is_void = true`)
- **Rejects** if the entry is itself a reversal (`void_of_id IS NOT NULL`) — cannot void a void
- Creates an equal and opposite reversing entry with `source_type = 'void'`
- Marks original entry as `is_void = true`
- **Inventory-aware:** if the original entry's `source_type` is `fifo_sale`, `lifo_sale`, or `inventory_receipt`, the void also restores `quantity_remaining` on affected inventory layers (or removes layers created by a receipt)
- Never deletes — preserves audit trail
- Returns: new reversal journal entry id

---

## File Structure

```
tools/accounting.py          — 21 @tool functions + 10 _primitives + schema helpers
tools/_output.py             — tool_result() (already planned)
agents/accounting.py         — MCP agent server
tests/test_tools_accounting.py
migrations/add_accounting_tables.sql
```

---

## Integration

- `tools/__init__.py` gains `from tools.accounting import ACCOUNTING_TOOLS` added to `ALL_TOOLS`
- `config.py` gains `"accounting": 8106` port and model assignment
- `run_agents.py` gains accounting agent entry
- `agents/dispatcher.py` gains accounting tool routing

---

## Out of Scope

- Depreciation schedules (future)
- Budgeting / budget-vs-actual (future)
- Multi-currency (future)
- Bank reconciliation (future)
- AR/AP aging reports (future)
- Accrual vs cash basis toggle (future)

The schema supports adding all of these later without breaking changes.
