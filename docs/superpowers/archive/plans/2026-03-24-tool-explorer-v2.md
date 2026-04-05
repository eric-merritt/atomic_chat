# Tool Explorer v2 — Implementation Plan (Layer 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the empty sidebar with a Tool Explorer (search + group cards) and add a center workspace for browsing tools, viewing parameters, and activating tool groups for the chat agent. Chat collapses to a slim column or input-bar-only when workspace is open.

**Architecture:** New `WorkspaceProvider` below `ChatProvider` manages layout state and active groups. Extends existing `GET /api/workflows` endpoint (in `main.py:261`) to include full tool metadata. New `POST /api/tools/select-group` for batch activation. Sidebar content replaced by `ToolExplorer` organism. Center panel is `ToolWorkspace` organism. ChatPage grid becomes dynamic (2–3 columns). Chain view button is visible but disabled (Layer 2).

**Tech Stack:** React 18, TypeScript, Tailwind v4, CSS custom properties, Vitest + React Testing Library (frontend). Flask, SQLAlchemy, Python 3.12 (backend).

**Spec:** `docs/superpowers/specs/2026-03-24-tool-explorer-v2-design.md`

---

## File Map

### Backend — New/Modified

| File | Action | Responsibility |
|------|--------|---------------|
| `routes/tools.py` | Create | `POST /api/tools/select-group` endpoint |
| `main.py` | Modify (L261-273, L213-219) | Extend existing `/api/workflows` to include tool metadata; register `tools_bp` blueprint |
| `config.py` | No change | Already has model config |

### Frontend — New

| File | Action | Responsibility |
|------|--------|---------------|
| `src/api/workflowGroups.ts` | Create | Fetch + cache workflow groups from API |
| `src/providers/WorkspaceProvider.tsx` | Create | Layout state, active groups, selected tools |
| `src/hooks/useWorkspace.ts` | Create | Context consumer for WorkspaceProvider |
| `src/components/organisms/ToolExplorer.tsx` | Create | Sidebar: search bar + group card list |
| `src/components/molecules/GroupCard.tsx` | Create | Dual-target card (expand + open workspace) |
| `src/components/organisms/ToolWorkspace.tsx` | Create | Center panel: stacked group sections |
| `src/components/atoms/ToolButton.tsx` | Create | Individual tool button |
| `src/components/molecules/ParamTable.tsx` | Create | Read-only + interactive parameter table |
| `src/components/molecules/ChatPopover.tsx` | Create | Messenger-style floating chat panel |

### Frontend — Modified

| File | Action | What changes |
|------|--------|-------------|
| `src/App.tsx` | Modify | Insert `WorkspaceProvider` below `ChatProvider` |
| `src/pages/ChatPage.tsx` | Modify | Dynamic grid columns, layout states, ChatPopover |
| `src/components/organisms/Sidebar.tsx` | Modify | Replace tool category content with `ToolExplorer` |

### Frontend — Retired (cleaned up in final task)

| File | Notes |
|------|-------|
| `src/components/molecules/ToolCategory.tsx` | Replaced by `GroupCard` |
| `src/components/molecules/ToolRow.tsx` | Replaced by `ToolButton` |

### Tests

| File | Tests for |
|------|-----------|
| `tests/test_tools_routes.py` | Backend workflow-groups + select-group endpoints |
| `src/api/__tests__/workflowGroups.test.ts` | API fetch + caching |
| `src/providers/__tests__/WorkspaceProvider.test.tsx` | Layout state transitions, group activation |
| `src/components/molecules/__tests__/GroupCard.test.tsx` | Expand/click targets, active indicator |
| `src/components/molecules/__tests__/ParamTable.test.tsx` | Read-only + interactive modes |
| `src/components/organisms/__tests__/ToolExplorer.test.tsx` | Search filtering, card rendering |
| `src/components/organisms/__tests__/ToolWorkspace.test.tsx` | Group sections, tool highlighting |

---

## Task 1: Backend — Extend `/api/workflows` with Tool Metadata

**Files:**
- Modify: `main.py` (L261-273 — `list_workflows` function)
- Test: `tests/test_tools_routes.py`

The existing `/api/workflows` endpoint returns group names, tooltips, and tool name lists. Extend it to include full tool metadata (description, params) using `TOOL_REGISTRY`.

**Note:** There is an existing `/api/workflows` endpoint at `main.py:261`. We extend it rather than creating a duplicate.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tools_routes.py`:

```python
"""Tests for tool-related API endpoints."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    """Create a test client with auth disabled and a mock current_user."""
    from main import app
    app.config["TESTING"] = True
    app.config["LOGIN_DISABLED"] = True

    mock_user = MagicMock()
    mock_user.is_authenticated = True
    mock_user.preferences = {}

    with patch("flask_login.utils._get_user", return_value=mock_user):
        with app.test_client() as c:
            yield c


def test_workflows_returns_all_groups(client):
    resp = client.get("/api/workflows")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "groups" in data
    names = [g["name"] for g in data["groups"]]
    assert "Filesystem" in names
    assert "Web Tools" in names
    assert "Accounting" in names


def test_workflows_includes_tool_metadata(client):
    resp = client.get("/api/workflows")
    data = resp.get_json()
    fs_group = next(g for g in data["groups"] if g["name"] == "Filesystem")
    assert "tooltip" in fs_group
    assert "tools" in fs_group
    assert len(fs_group["tools"]) > 0
    # Each tool should now be a dict with name, description, params
    tool = fs_group["tools"][0]
    assert isinstance(tool, dict)
    assert "name" in tool
    assert "description" in tool
    assert "params" in tool
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_routes.py -v`
Expected: FAIL — `tools` is a list of strings, not dicts with metadata

- [ ] **Step 3: Extend `list_workflows` in `main.py` (L261-273)**

Replace the existing `list_workflows` function:

```python
@app.route("/api/workflows", methods=["GET"])
@login_required
def list_workflows():
    """List available workflow groups with full tool metadata."""
    meta_by_name = {t["name"]: t for t in TOOL_REGISTRY}
    groups = []
    for name, group in WORKFLOW_GROUPS.items():
        tools = []
        for tool_name in group.tools:
            t = meta_by_name.get(tool_name)
            if t:
                tools.append({
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "params": t.get("params", {}),
                })
            else:
                tools.append({
                    "name": tool_name,
                    "description": "",
                    "params": {},
                })
        groups.append({
            "name": name,
            "tooltip": group.tooltip,
            "tools": tools,
        })
    return jsonify({"groups": groups})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_tools_routes.py main.py
git commit -m "feat: extend /api/workflows with full tool metadata"
```

---

## Task 2: Backend — `POST /api/tools/select-group` Endpoint

**Files:**
- Modify: `routes/tools.py`
- Test: `tests/test_tools_routes.py`

Batch-select or deselect all tools in a workflow group by name, so the frontend doesn't need N individual toggle calls.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_tools_routes.py`:

```python
def test_select_group_activates_tools(client):
    resp = client.post(
        "/api/tools/select-group",
        json={"group": "Code Search", "active": True},
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "selected" in data
    assert "grep" in data["selected"]
    assert "find" in data["selected"]
    assert "definition" in data["selected"]


def test_select_group_unknown_returns_404(client):
    resp = client.post(
        "/api/tools/select-group",
        json={"group": "Nonexistent"},
        content_type="application/json",
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_routes.py::test_select_group_activates_tools -v`
Expected: FAIL — 404 (endpoint doesn't exist)

- [ ] **Step 3: Create `routes/tools.py` with the endpoint**

```python
"""Tool selection endpoints."""

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from auth.db import get_db
from workflow_groups import WORKFLOW_GROUPS

tools_bp = Blueprint("tools", __name__, url_prefix="/api")


@tools_bp.route("/tools/select-group", methods=["POST"])
@login_required
def select_group():
    data = request.get_json(force=True)
    group_name = data.get("group", "")
    active = data.get("active", True)

    wg = WORKFLOW_GROUPS.get(group_name)
    if not wg:
        return jsonify({"error": f"Unknown group: {group_name}"}), 404

    db = get_db()
    prefs = dict(current_user.preferences or {})
    selected = set(prefs.get("selected_tools", []))

    if active:
        selected.update(wg.tools)
    else:
        selected -= set(wg.tools)

    prefs["selected_tools"] = sorted(selected)
    current_user.preferences = prefs
    db.commit()

    return jsonify({"ok": True, "selected": prefs["selected_tools"]})
```

- [ ] **Step 4: Register blueprint in `main.py` (after L219)**

```python
from routes.tools import tools_bp
app.register_blueprint(tools_bp)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_routes.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add routes/tools.py tests/test_tools_routes.py main.py
git commit -m "feat: add POST /api/tools/select-group endpoint"
```

---

## Task 3: Frontend — Workflow Groups API Client

**Files:**
- Create: `frontend/src/api/workflowGroups.ts`
- Test: `frontend/src/api/__tests__/workflowGroups.test.ts`

Fetch workflow groups from the new endpoint, cache the result.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/__tests__/workflowGroups.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchWorkflowGroups, selectGroup } from '../workflowGroups';

const MOCK_GROUPS = {
  groups: [
    {
      name: 'Filesystem',
      tooltip: 'File operations',
      tools: [
        { name: 'read', description: 'Read a file', params: { path: { type: 'string', required: true, description: 'File path' } } },
      ],
    },
  ],
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('fetchWorkflowGroups', () => {
  it('fetches and returns groups', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => MOCK_GROUPS,
    } as Response);

    const result = await fetchWorkflowGroups();
    expect(result.groups).toHaveLength(1);
    expect(result.groups[0].name).toBe('Filesystem');
    expect(fetch).toHaveBeenCalledWith('/api/workflows', expect.objectContaining({ credentials: 'include' }));
  });
});

describe('selectGroup', () => {
  it('posts group activation', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ ok: true, selected: ['read'] }),
    } as Response);

    const result = await selectGroup('Filesystem', true);
    expect(result.ok).toBe(true);
    expect(fetch).toHaveBeenCalledWith('/api/tools/select-group', expect.objectContaining({ method: 'POST' }));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx vitest run src/api/__tests__/workflowGroups.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Create `src/api/workflowGroups.ts`**

```typescript
const OPTS: RequestInit = { credentials: 'include' };
const HEADERS = { 'Content-Type': 'application/json' };

export interface ToolParam {
  type: string;
  required: boolean;
  description: string;
}

export interface WorkflowTool {
  name: string;
  description: string;
  params: Record<string, ToolParam>;
}

export interface WorkflowGroup {
  name: string;
  tooltip: string;
  tools: WorkflowTool[];
}

export interface WorkflowGroupsResponse {
  groups: WorkflowGroup[];
}

let _cache: WorkflowGroupsResponse | null = null;

export async function fetchWorkflowGroups(): Promise<WorkflowGroupsResponse> {
  if (_cache) return _cache;
  const resp = await fetch('/api/workflows', OPTS);
  if (!resp.ok) throw new Error(`Failed to fetch workflow groups: ${resp.status}`);
  const data: WorkflowGroupsResponse = await resp.json();
  _cache = data;
  return data;
}

export function clearWorkflowGroupsCache(): void {
  _cache = null;
}

export async function selectGroup(group: string, active: boolean): Promise<{ ok: boolean; selected: string[] }> {
  const resp = await fetch('/api/tools/select-group', {
    ...OPTS,
    method: 'POST',
    headers: HEADERS,
    body: JSON.stringify({ group, active }),
  });
  if (!resp.ok) throw new Error(`Failed to select group: ${resp.status}`);
  return resp.json();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx vitest run src/api/__tests__/workflowGroups.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/workflowGroups.ts frontend/src/api/__tests__/workflowGroups.test.ts
git commit -m "feat: add workflow groups API client with caching"
```

---

## Task 4: Frontend — WorkspaceProvider

**Files:**
- Create: `frontend/src/providers/WorkspaceProvider.tsx`
- Create: `frontend/src/hooks/useWorkspace.ts`
- Test: `frontend/src/providers/__tests__/WorkspaceProvider.test.tsx`

Manages layout state (default / workspace-chat / workspace-inputbar), active groups, and selected tool in workspace.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/providers/__tests__/WorkspaceProvider.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { WorkspaceProvider } from '../WorkspaceProvider';
import { useWorkspace } from '../../hooks/useWorkspace';
import type { ReactNode } from 'react';

// Mock the API
vi.mock('../../api/workflowGroups', () => ({
  fetchWorkflowGroups: vi.fn().mockResolvedValue({
    groups: [
      { name: 'Filesystem', tooltip: 'File ops', tools: [{ name: 'read', description: 'Read file', params: {} }] },
      { name: 'Web Tools', tooltip: 'Web ops', tools: [{ name: 'web_search', description: 'Search', params: {} }] },
    ],
  }),
  selectGroup: vi.fn().mockResolvedValue({ ok: true, selected: [] }),
}));

// Mock ToolProvider context
vi.mock('../../hooks/useTools', () => ({
  useTools: () => ({ categories: [], selected: [], toggleTool: vi.fn(), toggleCategory: vi.fn() }),
}));

const wrapper = ({ children }: { children: ReactNode }) => (
  <WorkspaceProvider>{children}</WorkspaceProvider>
);

describe('WorkspaceProvider', () => {
  it('starts in default layout', () => {
    const { result } = renderHook(() => useWorkspace(), { wrapper });
    expect(result.current.layout).toBe('default');
    expect(result.current.activeGroups).toEqual([]);
  });

  it('opens a group and transitions to workspace layout', async () => {
    const { result } = renderHook(() => useWorkspace(), { wrapper });
    await act(async () => {
      await result.current.openGroup('Filesystem');
    });
    expect(result.current.layout).toBe('workspace-chat');
    expect(result.current.activeGroups).toContain('Filesystem');
  });

  it('closes all groups and reverts to default', async () => {
    const { result } = renderHook(() => useWorkspace(), { wrapper });
    await act(async () => {
      await result.current.openGroup('Filesystem');
    });
    await act(async () => {
      await result.current.closeGroup('Filesystem');
    });
    expect(result.current.layout).toBe('default');
    expect(result.current.activeGroups).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx vitest run src/providers/__tests__/WorkspaceProvider.test.tsx`
Expected: FAIL — module not found

- [ ] **Step 3: Create `src/hooks/useWorkspace.ts`**

```typescript
import { useContext } from 'react';
import { WorkspaceContext } from '../providers/WorkspaceProvider';

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error('useWorkspace must be used within WorkspaceProvider');
  return ctx;
}
```

- [ ] **Step 4: Create `src/providers/WorkspaceProvider.tsx`**

```typescript
import { createContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { fetchWorkflowGroups, selectGroup, type WorkflowGroup } from '../api/workflowGroups';
import { useTools } from '../hooks/useTools';

export type LayoutState = 'default' | 'workspace-chat' | 'workspace-inputbar';

interface WorkspaceContextValue {
  layout: LayoutState;
  setLayout: (layout: LayoutState) => void;
  groups: WorkflowGroup[];
  activeGroups: string[];
  openGroup: (name: string) => Promise<void>;
  closeGroup: (name: string) => Promise<void>;
  selectedTool: string | null;
  selectTool: (name: string | null) => void;
}

export const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { refreshTools } = useTools();
  const [groups, setGroups] = useState<WorkflowGroup[]>([]);
  const [activeGroups, setActiveGroups] = useState<string[]>([]);
  const [layout, setLayout] = useState<LayoutState>('default');
  const [selectedTool, setSelectedTool] = useState<string | null>(null);

  useEffect(() => {
    fetchWorkflowGroups()
      .then((r) => setGroups(r.groups))
      .catch(() => {});
  }, []);

  const openGroup = useCallback(async (name: string) => {
    setActiveGroups((prev) => (prev.includes(name) ? prev : [...prev, name]));
    setLayout((prev) => (prev === 'default' ? 'workspace-chat' : prev));
    try {
      await selectGroup(name, true);
      await refreshTools(); // Sync ToolProvider in-memory state with DB
    } catch (e) {
      console.error('Failed to activate group:', e);
    }
  }, [refreshTools]);

  const closeGroup = useCallback(async (name: string) => {
    setActiveGroups((prev) => {
      const next = prev.filter((g) => g !== name);
      if (next.length === 0) setLayout('default');
      return next;
    });
    try {
      await selectGroup(name, false);
      await refreshTools(); // Sync ToolProvider in-memory state with DB
    } catch (e) {
      console.error('Failed to deactivate group:', e);
    }
  }, [refreshTools]);

  const selectToolCb = useCallback((name: string | null) => {
    setSelectedTool(name);
  }, []);

  return (
    <WorkspaceContext.Provider
      value={{
        layout,
        setLayout,
        groups,
        activeGroups,
        openGroup,
        closeGroup,
        selectedTool,
        selectTool: selectToolCb,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}
```

**Important:** This requires adding a `refreshTools` function to `ToolProvider`. In the same task, add to `ToolProvider.tsx`:

```typescript
const refreshTools = useCallback(async () => {
  const r = await apiFetchTools();
  if (r.data) setCategories(r.data);
}, []);
```

And include `refreshTools` in the context value. Update `useTools.ts` return type accordingly.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx vitest run src/providers/__tests__/WorkspaceProvider.test.tsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/providers/WorkspaceProvider.tsx frontend/src/hooks/useWorkspace.ts frontend/src/providers/__tests__/WorkspaceProvider.test.tsx
git commit -m "feat: add WorkspaceProvider with layout state and group management"
```

---

## Task 5: Wire WorkspaceProvider into App

**Files:**
- Modify: `frontend/src/App.tsx` (~L30-36, inside `AuthGate`)

Insert `WorkspaceProvider` below `ChatProvider`, above `WebSocketProvider`.

- [ ] **Step 1: Add import and wrap**

In `src/App.tsx`, add import:

```typescript
import { WorkspaceProvider } from './providers/WorkspaceProvider';
```

In the `AuthGate` component, wrap `WebSocketProvider` with `WorkspaceProvider`:

```typescript
<ChatProvider>
  <WorkspaceProvider>
    <WebSocketProvider enabled={false}>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
      </Routes>
    </WebSocketProvider>
  </WorkspaceProvider>
</ChatProvider>
```

- [ ] **Step 2: Verify app still compiles**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: wire WorkspaceProvider into App provider hierarchy"
```

---

## Task 6: Frontend — GroupCard Molecule

**Files:**
- Create: `frontend/src/components/molecules/GroupCard.tsx`
- Test: `frontend/src/components/molecules/__tests__/GroupCard.test.tsx`

Dual-target card: expand symbol toggles inline tool list, main area opens group in workspace.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/molecules/__tests__/GroupCard.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { GroupCard } from '../GroupCard';

const TOOLS = [
  { name: 'read', description: 'Read file', params: {} },
  { name: 'write', description: 'Write file', params: {} },
];

describe('GroupCard', () => {
  it('renders group name and tool count', () => {
    render(
      <GroupCard name="Filesystem" tooltip="File ops" tools={TOOLS} active={false} onOpen={vi.fn()} onClose={vi.fn()} />
    );
    expect(screen.getByText('Filesystem')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('calls onOpen when main area is clicked', () => {
    const onOpen = vi.fn();
    render(
      <GroupCard name="Filesystem" tooltip="File ops" tools={TOOLS} active={false} onOpen={onOpen} onClose={vi.fn()} />
    );
    fireEvent.click(screen.getByText('Filesystem'));
    expect(onOpen).toHaveBeenCalledWith('Filesystem');
  });

  it('expands to show tool names when expand button clicked', () => {
    render(
      <GroupCard name="Filesystem" tooltip="File ops" tools={TOOLS} active={false} onOpen={vi.fn()} onClose={vi.fn()} />
    );
    fireEvent.click(screen.getByTitle('Show tools'));
    expect(screen.getByText('read')).toBeInTheDocument();
    expect(screen.getByText('write')).toBeInTheDocument();
  });

  it('shows active indicator and close button when active', () => {
    render(
      <GroupCard name="Filesystem" tooltip="File ops" tools={TOOLS} active={true} onOpen={vi.fn()} onClose={vi.fn()} />
    );
    expect(screen.getByTitle('Remove group')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx vitest run src/components/molecules/__tests__/GroupCard.test.tsx`
Expected: FAIL — module not found

- [ ] **Step 3: Create `src/components/molecules/GroupCard.tsx`**

```typescript
import { useState } from 'react';
import type { WorkflowTool } from '../../api/workflowGroups';

interface GroupCardProps {
  name: string;
  tooltip: string;
  tools: WorkflowTool[];
  active: boolean;
  onOpen: (name: string) => void;
  onClose: (name: string) => void;
}

export function GroupCard({ name, tooltip, tools, active, onOpen, onClose }: GroupCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={`rounded-lg border transition-colors ${
        active
          ? 'border-[var(--accent)] shadow-[0_0_8px_color-mix(in_srgb,var(--accent)_40%,transparent)]'
          : 'border-[var(--glass-border)] hover:border-[var(--accent)]'
      } bg-[var(--glass-bg-solid)]`}
    >
      <div className="flex items-center">
        {/* Expand target */}
        <button
          className="flex items-center justify-center w-8 h-full shrink-0 cursor-pointer hover:bg-[var(--glass-highlight)] rounded-l-lg transition-colors"
          onClick={(e) => { e.stopPropagation(); setExpanded((p) => !p); }}
          title="Show tools"
        >
          <span
            className={`text-[var(--text-muted)] text-xs transition-transform ${expanded ? 'rotate-45' : ''}`}
          >
            ⊞
          </span>
        </button>

        {/* Main click target */}
        <button
          className="flex-1 flex items-center gap-2 px-2 py-2.5 cursor-pointer text-left min-w-0"
          onClick={() => onOpen(name)}
        >
          <div className="flex-1 min-w-0">
            <span className="text-sm font-medium text-[var(--text)] block truncate">{name}</span>
            <span className="text-[10px] text-[var(--text-muted)] block truncate">{tooltip}</span>
          </div>
          <span className="text-xs font-mono text-[var(--text-muted)] shrink-0">{tools.length}</span>
        </button>

        {/* Close button (when active) */}
        {active && (
          <button
            className="flex items-center justify-center w-6 h-6 mr-1 shrink-0 cursor-pointer text-[var(--text-muted)] hover:text-[#ff2020] transition-colors"
            onClick={(e) => { e.stopPropagation(); onClose(name); }}
            title="Remove group"
          >
            &times;
          </button>
        )}
      </div>

      {/* Expanded tool list */}
      {expanded && (
        <div className="border-t border-[var(--glass-border)] px-3 py-1.5">
          <div className="flex flex-wrap gap-1">
            {tools.map((t) => (
              <span
                key={t.name}
                className="text-[10px] font-mono text-[var(--accent)] px-1.5 py-0.5 rounded bg-[var(--glass-highlight)]"
              >
                {t.name}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx vitest run src/components/molecules/__tests__/GroupCard.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/molecules/GroupCard.tsx frontend/src/components/molecules/__tests__/GroupCard.test.tsx
git commit -m "feat: add GroupCard molecule with dual click targets"
```

---

## Task 7: Frontend — ToolExplorer Organism (Sidebar Content)

**Files:**
- Create: `frontend/src/components/organisms/ToolExplorer.tsx`
- Test: `frontend/src/components/organisms/__tests__/ToolExplorer.test.tsx`

Search bar + group card list. Replaces the tool category content in the sidebar.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/organisms/__tests__/ToolExplorer.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ToolExplorer } from '../ToolExplorer';
import { WorkspaceContext } from '../../../providers/WorkspaceProvider';
import type { LayoutState } from '../../../providers/WorkspaceProvider';

const GROUPS = [
  { name: 'Filesystem', tooltip: 'File ops', tools: [{ name: 'read', description: 'Read', params: {} }] },
  { name: 'Web Tools', tooltip: 'Web ops', tools: [{ name: 'web_search', description: 'Search', params: {} }] },
];

function renderWithContext(activeGroups: string[] = []) {
  const ctx = {
    layout: 'default' as LayoutState,
    setLayout: vi.fn(),
    groups: GROUPS,
    activeGroups,
    openGroup: vi.fn(),
    closeGroup: vi.fn(),
    selectedTool: null,
    selectTool: vi.fn(),
  };
  return { ...render(
    <WorkspaceContext.Provider value={ctx}>
      <ToolExplorer />
    </WorkspaceContext.Provider>
  ), ctx };
}

describe('ToolExplorer', () => {
  it('renders all group cards', () => {
    renderWithContext();
    expect(screen.getByText('Filesystem')).toBeInTheDocument();
    expect(screen.getByText('Web Tools')).toBeInTheDocument();
  });

  it('filters groups by search', () => {
    renderWithContext();
    fireEvent.change(screen.getByPlaceholderText('Search tools...'), { target: { value: 'web' } });
    expect(screen.queryByText('Filesystem')).not.toBeInTheDocument();
    expect(screen.getByText('Web Tools')).toBeInTheDocument();
  });

  it('shows empty state when no matches', () => {
    renderWithContext();
    fireEvent.change(screen.getByPlaceholderText('Search tools...'), { target: { value: 'zzzzz' } });
    expect(screen.getByText('No matching tools')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx vitest run src/components/organisms/__tests__/ToolExplorer.test.tsx`
Expected: FAIL

- [ ] **Step 3: Create `src/components/organisms/ToolExplorer.tsx`**

```typescript
import { useState, useMemo } from 'react';
import { useWorkspace } from '../../hooks/useWorkspace';
import { GroupCard } from '../molecules/GroupCard';

export function ToolExplorer() {
  const { groups, activeGroups, openGroup, closeGroup } = useWorkspace();
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search.trim()) return groups;
    const q = search.toLowerCase();
    return groups.filter(
      (g) =>
        g.name.toLowerCase().includes(q) ||
        g.tooltip.toLowerCase().includes(q) ||
        g.tools.some((t) => t.name.toLowerCase().includes(q)),
    );
  }, [groups, search]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Search */}
      <div className="px-2 pt-2 pb-1 shrink-0">
        <div className="relative">
          <input
            type="text"
            placeholder="Search tools..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full text-xs font-mono px-2 py-1.5 rounded-lg bg-[var(--glass-highlight)] border border-[var(--glass-border)] text-[var(--text)] placeholder:text-[var(--text-muted)] outline-none focus:border-[var(--accent)] transition-colors"
          />
          {search && (
            <button
              className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--accent)] cursor-pointer text-sm"
              onClick={() => setSearch('')}
              title="Clear search"
            >
              &times;
            </button>
          )}
        </div>
      </div>

      {/* Group cards */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center h-20">
            <span className="text-xs text-[var(--text-muted)]">No matching tools</span>
          </div>
        ) : (
          <div className="flex flex-col gap-2 pt-1">
            {filtered.map((g) => (
              <GroupCard
                key={g.name}
                name={g.name}
                tooltip={g.tooltip}
                tools={g.tools}
                active={activeGroups.includes(g.name)}
                onOpen={openGroup}
                onClose={closeGroup}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx vitest run src/components/organisms/__tests__/ToolExplorer.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/organisms/ToolExplorer.tsx frontend/src/components/organisms/__tests__/ToolExplorer.test.tsx
git commit -m "feat: add ToolExplorer organism with search and group cards"
```

---

## Task 8: Frontend — ToolButton Atom + ParamTable Molecule

**Files:**
- Create: `frontend/src/components/atoms/ToolButton.tsx`
- Create: `frontend/src/components/molecules/ParamTable.tsx`
- Test: `frontend/src/components/molecules/__tests__/ParamTable.test.tsx`

- [ ] **Step 1: Write the failing test for ParamTable**

Create `frontend/src/components/molecules/__tests__/ParamTable.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ParamTable } from '../ParamTable';

const PARAMS = {
  path: { type: 'string', required: true, description: 'File path' },
  lines: { type: 'integer', required: false, description: 'Number of lines' },
  recursive: { type: 'boolean', required: false, description: 'Recurse into dirs' },
};

describe('ParamTable', () => {
  it('renders param names and types in read-only mode', () => {
    render(<ParamTable params={PARAMS} interactive={false} values={{}} onChange={vi.fn()} />);
    expect(screen.getByText('path')).toBeInTheDocument();
    expect(screen.getByText('string')).toBeInTheDocument();
    expect(screen.getByText('integer')).toBeInTheDocument();
  });

  it('renders inputs in interactive mode', () => {
    render(<ParamTable params={PARAMS} interactive={true} values={{}} onChange={vi.fn()} />);
    const inputs = screen.getAllByRole('textbox');
    expect(inputs.length).toBeGreaterThan(0);
  });

  it('calls onChange when interactive value changes', () => {
    const onChange = vi.fn();
    render(<ParamTable params={PARAMS} interactive={true} values={{}} onChange={onChange} />);
    const input = screen.getAllByRole('textbox')[0];
    fireEvent.change(input, { target: { value: '/tmp/test' } });
    expect(onChange).toHaveBeenCalledWith('path', '/tmp/test');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx vitest run src/components/molecules/__tests__/ParamTable.test.tsx`
Expected: FAIL

- [ ] **Step 3: Create `src/components/atoms/ToolButton.tsx`**

```typescript
interface ToolButtonProps {
  name: string;
  selected: boolean;
  onClick: () => void;
}

export function ToolButton({ name, selected, onClick }: ToolButtonProps) {
  return (
    <button
      className={`px-2 py-1 text-xs font-mono rounded-md border cursor-pointer transition-colors ${
        selected
          ? 'border-[var(--accent)] bg-[var(--accent)] text-[var(--bg-base)]'
          : 'border-[var(--glass-border)] text-[var(--accent)] hover:border-[var(--accent)] bg-transparent'
      }`}
      onClick={onClick}
    >
      {name}
    </button>
  );
}
```

- [ ] **Step 4: Create `src/components/molecules/ParamTable.tsx`**

```typescript
import type { ToolParam } from '../../api/workflowGroups';

interface ParamTableProps {
  params: Record<string, ToolParam>;
  interactive: boolean;
  values: Record<string, unknown>;
  onChange: (name: string, value: unknown) => void;
}

export function ParamTable({ params, interactive, values, onChange }: ParamTableProps) {
  const entries = Object.entries(params);

  if (entries.length === 0) {
    return <span className="text-[10px] text-[var(--text-muted)] italic">No parameters</span>;
  }

  return (
    <table className="w-full text-[10px] font-mono border-collapse">
      <thead>
        <tr className="text-[var(--text-muted)]">
          <th className="text-left py-1 pr-2">Name</th>
          <th className="text-left py-1 pr-2">Type</th>
          <th className="text-left py-1 pr-2">Req</th>
          {interactive ? (
            <th className="text-left py-1">Value</th>
          ) : (
            <th className="text-left py-1">Description</th>
          )}
        </tr>
      </thead>
      <tbody>
        {entries.map(([name, param]) => (
          <tr key={name} className="border-t border-[var(--glass-border)]">
            <td className="py-1 pr-2 text-[var(--accent)]">{name}</td>
            <td className="py-1 pr-2 text-[var(--text-muted)]">{param.type}</td>
            <td className="py-1 pr-2">{param.required ? '✓' : ''}</td>
            {interactive ? (
              <td className="py-1">
                {param.type === 'boolean' ? (
                  <label className="flex items-center gap-1 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={!!values[name]}
                      onChange={(e) => onChange(name, e.target.checked)}
                    />
                  </label>
                ) : param.type === 'integer' || param.type === 'number' ? (
                  <input
                    type="number"
                    value={values[name] as number ?? ''}
                    onChange={(e) => onChange(name, e.target.value ? Number(e.target.value) : '')}
                    className="w-full bg-transparent border-b border-[var(--glass-border)] text-[var(--text)] outline-none focus:border-[var(--accent)]"
                  />
                ) : (
                  <input
                    type="text"
                    value={values[name] as string ?? ''}
                    onChange={(e) => onChange(name, e.target.value)}
                    className="w-full bg-transparent border-b border-[var(--glass-border)] text-[var(--text)] outline-none focus:border-[var(--accent)]"
                    placeholder={param.description}
                  />
                )}
              </td>
            ) : (
              <td className="py-1 text-[var(--text-muted)]">{param.description}</td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx vitest run src/components/molecules/__tests__/ParamTable.test.tsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/atoms/ToolButton.tsx frontend/src/components/molecules/ParamTable.tsx frontend/src/components/molecules/__tests__/ParamTable.test.tsx
git commit -m "feat: add ToolButton atom and ParamTable molecule"
```

---

## Task 9: Frontend — ToolWorkspace Organism

**Files:**
- Create: `frontend/src/components/organisms/ToolWorkspace.tsx`
- Test: `frontend/src/components/organisms/__tests__/ToolWorkspace.test.tsx`

Center panel with stacked group sections, tool buttons, detail area with params.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/organisms/__tests__/ToolWorkspace.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ToolWorkspace } from '../ToolWorkspace';
import { WorkspaceContext } from '../../../providers/WorkspaceProvider';
import type { LayoutState } from '../../../providers/WorkspaceProvider';

const GROUPS = [
  {
    name: 'Filesystem',
    tooltip: 'File ops',
    tools: [
      { name: 'read', description: 'Read a file from disk', params: { path: { type: 'string', required: true, description: 'File path' } } },
      { name: 'write', description: 'Write to a file', params: { path: { type: 'string', required: true, description: 'File path' }, content: { type: 'string', required: true, description: 'Content' } } },
    ],
  },
];

function renderWithContext() {
  const ctx = {
    layout: 'workspace-chat' as LayoutState,
    setLayout: vi.fn(),
    groups: GROUPS,
    activeGroups: ['Filesystem'],
    openGroup: vi.fn(),
    closeGroup: vi.fn(),
    selectedTool: null,
    selectTool: vi.fn(),
  };
  return { ...render(
    <WorkspaceContext.Provider value={ctx}>
      <ToolWorkspace />
    </WorkspaceContext.Provider>
  ), ctx };
}

describe('ToolWorkspace', () => {
  it('renders active group sections', () => {
    renderWithContext();
    expect(screen.getByText('Filesystem')).toBeInTheDocument();
  });

  it('renders tool buttons for active groups', () => {
    renderWithContext();
    expect(screen.getByText('read')).toBeInTheDocument();
    expect(screen.getByText('write')).toBeInTheDocument();
  });

  it('shows tool detail when tool button is clicked', () => {
    const { ctx } = renderWithContext();
    fireEvent.click(screen.getByText('read'));
    expect(ctx.selectTool).toHaveBeenCalledWith('read');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx vitest run src/components/organisms/__tests__/ToolWorkspace.test.tsx`
Expected: FAIL

- [ ] **Step 3: Create `src/components/organisms/ToolWorkspace.tsx`**

```typescript
import { useState, useCallback } from 'react';
import { useWorkspace } from '../../hooks/useWorkspace';
import { ToolButton } from '../atoms/ToolButton';
import { ParamTable } from '../molecules/ParamTable';
import type { WorkflowTool } from '../../api/workflowGroups';

export function ToolWorkspace() {
  const { groups, activeGroups, closeGroup, selectedTool, selectTool } = useWorkspace();
  const [interactive, setInteractive] = useState(false);
  const [paramValues, setParamValues] = useState<Record<string, unknown>>({});

  const activeGroupData = groups.filter((g) => activeGroups.includes(g.name));

  const handleParamChange = useCallback((name: string, value: unknown) => {
    setParamValues((prev) => ({ ...prev, [name]: value }));
  }, []);

  // Find the selected tool's full data
  let selectedToolData: WorkflowTool | null = null;
  for (const g of activeGroupData) {
    const found = g.tools.find((t) => t.name === selectedTool);
    if (found) { selectedToolData = found; break; }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden bg-[var(--bg-base)]">
      <div className="flex-1 overflow-y-auto">
        {activeGroupData.map((g) => (
          <div key={g.name} className="border-b border-[var(--glass-border)]">
            {/* Group header */}
            <div className="flex items-center px-4 py-2 bg-[var(--glass-bg-solid)]">
              <span className="flex-1 text-sm font-semibold text-[var(--text)]">{g.name}</span>
              <button
                className="text-[var(--text-muted)] hover:text-[#ff2020] cursor-pointer transition-colors text-sm"
                onClick={() => closeGroup(g.name)}
                title="Close group"
              >
                &times;
              </button>
            </div>

            {/* Tool buttons */}
            <div className="flex flex-wrap gap-2 px-4 py-3">
              {g.tools.map((t) => (
                <ToolButton
                  key={t.name}
                  name={t.name}
                  selected={selectedTool === t.name}
                  onClick={() => selectTool(selectedTool === t.name ? null : t.name)}
                />
              ))}
            </div>

            {/* Tool detail (if a tool in this group is selected) */}
            {selectedToolData && g.tools.some((t) => t.name === selectedTool) && (
              <div className="px-4 pb-4 border-t border-[var(--glass-border)]">
                <div className="flex items-center justify-between py-2">
                  <span className="text-xs font-mono text-[var(--accent)]">{selectedToolData.name}</span>
                  <div className="flex items-center gap-2">
                    <button
                      className="text-[10px] text-[var(--text-muted)] hover:text-[var(--accent)] cursor-pointer transition-colors"
                      onClick={() => setInteractive((p) => !p)}
                    >
                      {interactive ? '📋 Read-only' : '⚡ Interactive'}
                    </button>
                    {/* Push to chain — disabled for Layer 1 */}
                    <button
                      className="text-[10px] text-[var(--text-muted)] opacity-50 cursor-not-allowed"
                      title="Chain view coming soon"
                      disabled
                    >
                      ⛓→
                    </button>
                  </div>
                </div>
                <p className="text-[10px] text-[var(--text-muted)] mb-2">{selectedToolData.description}</p>
                <ParamTable
                  params={selectedToolData.params}
                  interactive={interactive}
                  values={paramValues}
                  onChange={handleParamChange}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx vitest run src/components/organisms/__tests__/ToolWorkspace.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/organisms/ToolWorkspace.tsx frontend/src/components/organisms/__tests__/ToolWorkspace.test.tsx
git commit -m "feat: add ToolWorkspace organism with group sections and tool detail"
```

---

## Task 10: Frontend — ChatPopover Molecule

**Files:**
- Create: `frontend/src/components/molecules/ChatPopover.tsx`

Messenger-style floating chat panel, lightweight message list.

- [ ] **Step 1: Create `src/components/molecules/ChatPopover.tsx`**

```typescript
import { useRef, useEffect } from 'react';
import { useChat } from '../../hooks/useChat';

interface ChatPopoverProps {
  open: boolean;
  onClose: () => void;
}

export function ChatPopover({ open, onClose }: ChatPopoverProps) {
  const { messages } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [open, messages]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={popoverRef}
      className="fixed bottom-16 right-4 w-80 h-96 rounded-xl border border-[var(--accent)] bg-[var(--glass-bg-solid)] backdrop-blur-xl shadow-[0_8px_32px_rgba(0,0,0,0.3)] flex flex-col z-50 animate-[msgIn_0.15s_ease-out]"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--glass-border)]">
        <span className="text-xs font-semibold text-[var(--accent)]">Chat</span>
        <button
          className="text-[var(--text-muted)] hover:text-[var(--accent)] cursor-pointer text-sm"
          onClick={onClose}
        >
          &times;
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-2 flex flex-col gap-2">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`text-[10px] font-mono p-2 rounded-lg max-w-[90%] ${
              m.role === 'user'
                ? 'self-end bg-[var(--msg-user)] text-[var(--text)]'
                : 'self-start bg-[var(--msg-assistant)] text-[var(--text)]'
            }`}
          >
            {typeof m.content === 'string'
              ? m.content.slice(0, 500) + (m.content.length > 500 ? '…' : '')
              : '[Tool result]'}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx tsc --noEmit`
Expected: No errors (may need adjustments based on `messages` type from `useChat`)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/molecules/ChatPopover.tsx
git commit -m "feat: add ChatPopover molecule for messenger-style floating chat"
```

---

## Task 11: Frontend — Update Sidebar to Use ToolExplorer

**Files:**
- Modify: `frontend/src/components/organisms/Sidebar.tsx`

Replace the current tool category content with `ToolExplorer`.

- [ ] **Step 1: Rewrite `Sidebar.tsx`**

Replace the full file content with:

```typescript
import { Icon } from '../atoms/Icon';
import { ToolExplorer } from './ToolExplorer';

interface SidebarProps {
  expanded: boolean;
  onToggle: () => void;
}

export function Sidebar({ expanded, onToggle }: SidebarProps) {
  return (
    <div
      className={`flex border border-[var(--accent)] rounded-[14px] m-2 overflow-hidden shadow-[0_4px_24px_rgba(0,0,0,0.15)] transition-colors ${
        expanded ? 'backdrop-blur-md' : 'bg-transparent hover:backdrop-blur-md cursor-pointer'
      }`}
    >
      {/* Main content column */}
      <div className="flex-1 flex flex-col overflow-hidden" onClick={expanded ? undefined : onToggle}>
        <div className="text-sm font-semibold text-[var(--text)] py-2 pl-4 text-center underline">
          Tools
        </div>
        {expanded && <ToolExplorer />}
      </div>

      {/* Chevron column */}
      <div
        className="flex items-center justify-center cursor-pointer transition-colors"
        onClick={onToggle}
        title="Toggle tools"
      >
        <Icon
          name="chevron"
          size={18}
          className={`text-[var(--accent)] transition-all ${expanded ? 'rotate-180' : ''}`}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Run existing tests**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx vitest run`
Expected: All tests pass (some old Sidebar tests may need updating — fix as needed)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/organisms/Sidebar.tsx
git commit -m "refactor: replace Sidebar tool categories with ToolExplorer"
```

---

## Task 12: Frontend — Dynamic Grid Layout in ChatPage

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx`

ChatPage grid becomes dynamic based on workspace layout state. Adds ToolWorkspace panel, ChatPopover, and layout transitions.

- [ ] **Step 1: Update `ChatPage.tsx`**

Key changes to the existing file:

1. Import `useWorkspace`, `ToolWorkspace`, `ChatPopover`
2. Compute `gridTemplateColumns` from `layout` state
3. Conditionally render `ToolWorkspace` when layout is not `default`
4. Conditionally render slim chat or hide chat based on layout
5. Add `ChatPopover` with trigger button in input bar area
6. InputBar uses `grid-column: 1 / -1`

```typescript
import { useState, useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useChat } from '../hooks/useChat';
import { useWorkspace } from '../hooks/useWorkspace';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { TopBar } from '../components/organisms/TopBar';
import { Sidebar } from '../components/organisms/Sidebar';
import { MessageList } from '../components/organisms/MessageList';
import { InputBar } from '../components/organisms/InputBar';
import { TaskList } from '../components/organisms/TaskList';
import { ToolWorkspace } from '../components/organisms/ToolWorkspace';
import { ChatPopover } from '../components/molecules/ChatPopover';
import { Lightbox } from '../components/organisms/Lightbox';
import { ParticleCanvas } from '../components/atoms/ParticleCanvas';
import { useTheme } from '../hooks/useTheme';

export function ChatPage() {
  const { theme } = useTheme();
  const { layout } = useWorkspace();
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
  const [lightbox, setLightbox] = useState<{ src: string; caption: string } | null>(null);
  const [chatPopoverOpen, setChatPopoverOpen] = useState(false);
  const [searchParams] = useSearchParams();
  const { loadConversation } = useChat();

  useEffect(() => {
    const convId = searchParams.get('conversation');
    if (convId) loadConversation(convId);
  }, [searchParams, loadConversation]);

  const handleImageClick = useCallback((src: string, caption: string) => {
    setLightbox({ src, caption });
  }, []);

  const sidebarWidth = sidebarExpanded ? '22rem' : '6rem';

  const gridColumns = (() => {
    switch (layout) {
      case 'workspace-chat':
        return `${sidebarWidth} 1fr 22rem`;
      case 'workspace-inputbar':
        return `${sidebarWidth} 1fr`;
      default:
        return `${sidebarWidth} 1fr`;
    }
  })();

  const showChat = layout !== 'workspace-inputbar';

  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
      <ParticleCanvas theme={theme.id} />
      <ErrorBoundary>
        <TopBar />
      </ErrorBoundary>

      <div
        className="flex-1 grid grid-rows-[1fr_auto] transition-[grid-template-columns] duration-300 ease-in-out overflow-hidden"
        style={{ gridTemplateColumns: gridColumns }}
      >
        {/* Sidebar — always present */}
        <ErrorBoundary>
          <Sidebar
            expanded={sidebarExpanded}
            onToggle={() => setSidebarExpanded((p) => !p)}
          />
        </ErrorBoundary>

        {/* Center: Chat (default) or Workspace */}
        {layout === 'default' ? (
          <ErrorBoundary>
            <MessageList onImageClick={handleImageClick} />
          </ErrorBoundary>
        ) : (
          <ErrorBoundary>
            <ToolWorkspace />
          </ErrorBoundary>
        )}

        {/* Right column: slim chat (workspace-chat layout only) */}
        {layout === 'workspace-chat' && (
          <ErrorBoundary>
            <div className="overflow-hidden border-l border-[var(--glass-border)]">
              <MessageList onImageClick={handleImageClick} />
            </div>
          </ErrorBoundary>
        )}

        {/* Bottom row: spans all columns */}
        <div style={{ gridColumn: '1 / -1' }} className="flex items-stretch">
          <ErrorBoundary>
            <div className="flex items-stretch m-2">
              <TaskList sidebarExpanded={sidebarExpanded} />
            </div>
          </ErrorBoundary>
          <ErrorBoundary>
            <div className="flex-1 flex items-stretch">
              <InputBar />
              {layout === 'workspace-inputbar' && (
                <button
                  className="flex items-center justify-center w-10 shrink-0 cursor-pointer text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors text-lg"
                  onClick={() => setChatPopoverOpen((p) => !p)}
                  title="Open chat"
                >
                  💬
                </button>
              )}
            </div>
          </ErrorBoundary>
        </div>
      </div>

      {/* Chat popover */}
      <ChatPopover open={chatPopoverOpen} onClose={() => setChatPopoverOpen(false)} />

      {lightbox && (
        <Lightbox
          src={lightbox.src}
          caption={lightbox.caption}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Manual smoke test**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npm run dev`

1. Sidebar should show ToolExplorer with search + group cards
2. Clicking a group card should open the workspace and push chat to slim column
3. Tool buttons should be visible in workspace
4. Clicking a tool should show its params

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx
git commit -m "feat: dynamic grid layout with workspace and chat states"
```

---

## Task 13: Cleanup — Remove Retired Components

**Files:**
- Delete: `frontend/src/components/molecules/ToolCategory.tsx`
- Delete: `frontend/src/components/molecules/ToolRow.tsx`
- Clean up: any tests referencing these files

- [ ] **Step 1: Check for imports of retired files**

Search for imports of `ToolCategory` and `ToolRow` in the codebase. The only consumer was `Sidebar.tsx` which was already rewritten. Remove any remaining references.

- [ ] **Step 2: Delete the files (if they exist)**

```bash
rm -f frontend/src/components/molecules/ToolCategory.tsx
rm -f frontend/src/components/molecules/ToolRow.tsx
rm -f frontend/src/components/molecules/__tests__/ToolCategory.test.tsx
rm -f frontend/src/components/molecules/__tests__/ToolRow.test.tsx
```

Note: These files may already be absent from the working tree. The `-f` flag handles this gracefully.

- [ ] **Step 3: Verify all tests pass**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx vitest run`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add -A frontend/src/components/molecules/
git commit -m "chore: remove retired ToolCategory and ToolRow components"
```

---

## Task 14: Full Integration Test

- [ ] **Step 1: Run all frontend tests**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx vitest run`
Expected: All pass

- [ ] **Step 2: Run all backend tests**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest -v`
Expected: All pass

- [ ] **Step 3: Type check**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Manual end-to-end test**

Start both servers:
- Backend: `cd /home/ermer/devproj/python/atomic_chat && uv run python main.py`
- Frontend: `cd /home/ermer/devproj/python/atomic_chat/frontend && npm run dev`

Test flow:
1. Sidebar shows ToolExplorer with search bar and 8 group cards
2. Search filters groups by name/tool name
3. Expand button (`⊞`) shows tool list inline on card
4. Clicking a group card opens workspace, chat shifts to slim column
5. Workspace shows group header, tool buttons, close (×)
6. Clicking a tool button highlights it and shows description + param table
7. Interactive toggle switches param table to editable inputs
8. Closing all groups reverts to default chat layout
9. Multiple groups can be open simultaneously in workspace
10. Chat popover works when chat is in input-bar-only mode

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix: integration test fixes for Tool Explorer v2 Layer 1"
```
