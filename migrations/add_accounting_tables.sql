-- migrations/add_accounting_tables.sql
-- Accounting module: 6 tables, 4 enums

-- Enums
CREATE TYPE account_type AS ENUM ('asset', 'liability', 'equity', 'revenue', 'expense');
CREATE TYPE normal_balance AS ENUM ('debit', 'credit');
CREATE TYPE item_type AS ENUM ('goods', 'service');
CREATE TYPE source_type AS ENUM ('manual', 'fifo_sale', 'lifo_sale', 'inventory_receipt', 'period_close', 'void');

-- Ledgers
CREATE TABLE ledgers (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Accounts
CREATE TABLE accounts (
    id SERIAL PRIMARY KEY,
    ledger_id INTEGER NOT NULL REFERENCES ledgers(id) ON DELETE CASCADE,
    account_type account_type NOT NULL,
    name VARCHAR(255) NOT NULL,
    account_number VARCHAR(20),
    parent_id INTEGER REFERENCES accounts(id),
    normal_balance normal_balance NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_account_ledger_name UNIQUE (ledger_id, name),
    CONSTRAINT uq_account_ledger_number UNIQUE (ledger_id, account_number)
);

-- Journal Entries
CREATE TABLE journal_entries (
    id SERIAL PRIMARY KEY,
    ledger_id INTEGER NOT NULL REFERENCES ledgers(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    memo TEXT NOT NULL,
    is_void BOOLEAN NOT NULL DEFAULT FALSE,
    void_of_id INTEGER REFERENCES journal_entries(id),
    source_type source_type NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Journal Lines
CREATE TABLE journal_lines (
    id SERIAL PRIMARY KEY,
    journal_entry_id INTEGER NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    debit NUMERIC(15,2) NOT NULL DEFAULT 0,
    credit NUMERIC(15,2) NOT NULL DEFAULT 0,
    memo TEXT,
    CONSTRAINT ck_journal_line_one_side CHECK (debit >= 0 AND credit >= 0 AND (debit > 0) != (credit > 0))
);

-- Inventory Items
CREATE TABLE inventory_items (
    id SERIAL PRIMARY KEY,
    ledger_id INTEGER NOT NULL REFERENCES ledgers(id) ON DELETE CASCADE,
    item_type item_type NOT NULL,
    sku VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    default_sale_price NUMERIC(15,2),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_inventory_ledger_sku UNIQUE (ledger_id, sku)
);

-- Inventory Layers
CREATE TABLE inventory_layers (
    id SERIAL PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
    journal_entry_id INTEGER REFERENCES journal_entries(id),
    quantity_purchased NUMERIC(15,4) NOT NULL,
    quantity_remaining NUMERIC(15,4) NOT NULL,
    unit_cost NUMERIC(15,4) NOT NULL,
    received_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_accounts_ledger ON accounts(ledger_id);
CREATE INDEX idx_journal_entries_ledger_date ON journal_entries(ledger_id, date);
CREATE INDEX idx_journal_lines_entry ON journal_lines(journal_entry_id);
CREATE INDEX idx_journal_lines_account ON journal_lines(account_id);
CREATE INDEX idx_inventory_items_ledger ON inventory_items(ledger_id);
CREATE INDEX idx_inventory_layers_item ON inventory_layers(item_id);
