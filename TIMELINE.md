# Atomic Chat — Development Timeline

> From a single-file CLI experiment to a full-stack multi-agent platform.

---

## 2026-03-10 — Genesis

```
  ┌─────────────────────────────────────────────────┐
  │  486ec0e  Initial commit                        │
  │           A monolithic Python script pairing     │
  │           LangChain + Ollama with 20 CLI tools   │
  └────────────────────────┬────────────────────────┘
                           │
                           ▼
  ┌─────────────────────────────────────────────────┐
  │  Subagent Architecture                          │
  │  ├─ Design spec + implementation plan           │
  │  ├─ tools.py split → tools/ package             │
  │  │   ├── filesystem   (file I/O, tree, copy)    │
  │  │   ├── codesearch   (grep, find, definitions) │
  │  │   ├── web          (search, fetch, eBay)     │
  │  │   └── marketplace  (domain-specific)         │
  │  ├─ MCP agent servers per domain                │
  │  ├─ Dispatcher + analyst agent w/ rate limiting │
  │  └─ Agent proxy endpoints + nginx config        │
  └────────────────────────┬────────────────────────┘
                           │
```

---

## 2026-03-16 — The Frontend

```
                           │
                           ▼
  ┌─────────────────────────────────────────────────┐
  │  React + TypeScript + Tailwind v4               │
  │  ├─ Atomic design: atoms → molecules → organisms│
  │  ├─ Pure data atoms (Message, Tool, Model, etc.)│
  │  ├─ API adapters (chat, models, tools, history) │
  │  ├─ Hook + Provider layer                       │
  │  │   ├── useChat / ChatProvider                 │
  │  │   ├── useModels / ModelProvider              │
  │  │   ├── useTools / ToolProvider                │
  │  │   ├── useStream (NDJSON line parser)         │
  │  │   ├── useTheme / ThemeProvider               │
  │  │   └── useWebSocket / WebSocketProvider       │
  │  ├─ ParticleCanvas animated background          │
  │  └─ Grid layout with animated sidebar           │
  └────────────────────────┬────────────────────────┘
                           │
```

---

## 2026-03-17 — Identity & Persistence

```
                           │
                           ▼
  ┌─────────────────────────────────────────────────┐
  │  ★ Rebranded to "Atomic Chat"                   │
  │                                                 │
  │  Authentication                                 │
  │  ├─ Local auth (bcrypt)                         │
  │  ├─ GitHub OAuth                                │
  │  └─ Google OAuth                                │
  │                                                 │
  │  Conversations & Preferences                    │
  │  ├─ Conversation + ConversationMessage models   │
  │  ├─ CRUD API with pagination                    │
  │  ├─ Per-user tool selection via preferences     │
  │  ├─ Message persistence during streaming        │
  │  └─ Preferences JSONB column on User            │
  │                                                 │
  │  Dashboard                                      │
  │  ├─ ProfilePanel, ApiKeyPanel, ConnectionsPanel │
  │  ├─ ConversationList + ConversationItem         │
  │  ├─ UserMenu dropdown in TopBar                 │
  │  └─ Avatar, Modal, DropdownMenu atoms           │
  └────────────────────────┬────────────────────────┘
                           │
```

---

## 2026-03-18 — Cross-Platform & Stability

```
                           │
                           ▼
  ┌─────────────────────────────────────────────────┐
  │  Client Agent Installers                        │
  │  ├─ get-agent.sh  (bash, curl/wget)             │
  │  ├─ get-agent.ps1 (PowerShell, iex-safe)        │
  │  └─ Windows Python path scanning                │
  │                                                 │
  │  Global State Fix                               │
  │  └─ Design spec for isolating per-user state    │
  └────────────────────────┬────────────────────────┘
                           │
```

---

## 2026-03-20 — Accounting Engine

```
                           │
                           ▼
  ┌─────────────────────────────────────────────────┐
  │  21 Accounting Tools                            │
  │  ├─ 6 new database tables (migration)           │
  │  ├─ Ledger setup & account management      (5)  │
  │  ├─ Journal entries, search, void          (4)  │
  │  ├─ Inventory registration & receiving     (4)  │
  │  ├─ FIFO/LIFO costing & valuation          (3)  │
  │  ├─ Period close & financial reporting      (5)  │
  │  ├─ Standardized tool output helper             │
  │  └─ Full test coverage                          │
  └────────────────────────┬────────────────────────┘
                           │
```

---

## 2026-03-21 — Cleanup & Intelligence

```
                           │
                           ▼
  ┌─────────────────────────────────────────────────┐
  │  Dead Code Removal                              │
  │  ├─ Removed agents/, index.py, run_agents.py    │
  │  └─ Cleaned config.py (dead agent constants)    │
  │                                                 │
  │  Smart Tool Selection                           │
  │  ├─ Tool pre-pass — lightweight LLM picks       │
  │  │   relevant tools per turn                    │
  │  └─ Context pipeline — conversation history     │
  │      replay and serialization                   │
  │                                                 │
  │  Wiring                                         │
  │  ├─ Pre-pass integrated into main.py            │
  │  ├─ Context pipeline into chat_stream           │
  │  ├─ Model name in agent cache key               │
  │  ├─ Frontend parses conversation_id from NDJSON │
  │  └─ dotenv loading + Flask secret_key           │
  └────────────────────────┬────────────────────────┘
                           │
```

---

## 2026-03-22 — Agent Loop v2 & Accounting UI

```
                           │
                           ▼
  ┌─────────────────────────────────────────────────┐
  │  Agent Loop Rewrite                             │
  │  ├─ New streaming agent loop architecture       │
  │  ├─ Browser tools (Selenium + BeautifulSoup)    │
  │  └─ Accounting REST routes                      │
  │                                                 │
  │  Accounting UI                                  │
  │  ├─ Frontend accounting components              │
  │  └─ Tool activity panel                         │
  │                                                 │
  │  Design                                         │
  │  ├─ Tool explorer + 3-column layout spec        │
  │  └─ MCP conversion design spec                  │
  └────────────────────────┬────────────────────────┘
                           │
```

---

## 2026-03-23 — The Rename

```
                           │
                           ▼
  ┌─────────────────────────────────────────────────┐
  │  agentic_w_langchain_ollama → atomic_chat       │
  │                                                 │
  │  Project identity now matches the brand          │
  │  established on 2026-03-17.                      │
  └─────────────────────────────────────────────────┘
```

---

*107 commits. 13 days. One vision.*
