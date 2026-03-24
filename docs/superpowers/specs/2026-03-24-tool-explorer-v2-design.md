# Tool Explorer v2 — Design Spec

**Date:** 2026-03-24
**Supersedes:** 2026-03-22-tool-explorer-3col-layout-design.md
**Goal:** Replace the empty sidebar with a full Tool Explorer — search, group cards, a center workspace for browsing/selecting tools, a chain view for building tool pipelines, and collapsible chat states.

---

## 1. Layout States

Three layout states managed by `WorkspaceProvider`:

### Default (no workspace open)

```
[Sidebar]  [Chat (full width)          ]
           [InputBar                    ]
```

Chat fills the entire center. Sidebar shows ToolExplorer (search + group cards). This is the normal chat experience.

### Workspace + Chat Column

```
[Sidebar]  [Workspace        ]  [Chat (slim)]
           [InputBar                         ]
```

Chat shrinks to a sidebar-width column on the right. Workspace fills the center. Input bar spans the full bottom. Chain view not yet open (or collapsed into the slim chat column area).

### Workspace + Chain + Input Bar Only

```
[Sidebar]  [Workspace   ]  [ChainView   ]
           [InputBar  (full width)  [💬] ]
```

Chat collapses entirely. Chain view takes the right column. Input bar at bottom full-width with:
- Left: input field (agent instruction or chat message)
- Mode indicator: toggle between "Chat" and "Agent" mode
- Right edge: click target (`💬`) that opens a ChatPopover — floating messenger-style panel anchored bottom-right

### Chain View Collapsed Variant

```
[Sidebar]  [Workspace              ]  [Chain ▸]
           [InputBar                    [💬]   ]
```

Chain view collapses to sidebar-width strip showing step count and small tool icons. Expand button restores full panel.

Closing all workspace groups reverts to Default layout.

---

## 2. Sidebar — ToolExplorer

Replaces the current empty sidebar content entirely.

### Search Bar

- Top of sidebar, always visible
- Debounced instant filter — filters group cards and tools within expanded groups by name
- No API call; group/tool registry is static data from `workflow_groups.py`

### Group Cards

Scrollable list below search.

**Card states:**
- **Collapsed (default):** Group name, tool count badge, active indicator (accent glow/dot when group's tools are activated for the agent)
- **Expanded:** Shows tool names as compact list below the card header

**Dual click targets:**
- **Expand target:** Unique symbol (e.g., `⊞` grid icon) on one edge. Clicking toggles inline tool name list within the sidebar.
- **Main click target:** Rest of the card. Opens/adds the group to the workspace center panel.

**Active indicator:** When a group's tools are activated for the agent, the card shows an accent border or glow. An X badge appears to remove the group from workspace and deactivate its tools.

**Draggable (Layer 3):**
- Within sidebar: reorders group cards
- Over chat area left 1/3: chat shrinks to slim column, workspace outline appears
- Over chat area right 2/3: chat collapses to input bar, workspace takes full center
- Moving out of chat area: layout preview reverts
- Drop: commits layout + activates group tools for agent

---

## 3. Workspace — ToolWorkspace

Center panel. Appears when one or more groups are opened from the sidebar.

### Stacked Group Sections

Each active group gets a section in the workspace, visually separated by borders/gaps.

**Group section contents:**
- **Header:** Group name + X button (removes from workspace, deactivates tools)
- **Tool buttons:** Grid/flow layout, one button per tool. Click to highlight/select. Multiple tools can be highlighted across groups.
- **Tool detail area:** When a tool is highlighted, its description and parameter table appear below the buttons in that section.

### Parameter Table

Displays for the highlighted tool:
- Columns: Name, Type, Required, Description
- Read-only by default

**Interactive toggle:** Switches parameter table to editable inputs matching types (text fields, number inputs, boolean toggles). Pre-fills params for when the tool is pushed to the chain.

### Push to Chain

A highlighted tool shows a chain icon with right chevron (`⛓→`). Clicking pushes the tool (with any pre-filled params from interactive mode) to the chain view.

Workspace scrolls independently from sidebar and chain view.

---

## 4. Chain View (Layer 2)

Right column pipeline builder.

### Two States

- **Collapsed:** Sidebar-width strip. Shows step count, small tool icons stacked vertically, expand button.
- **Expanded:** Full panel with the chain pipeline.

### Chain Link Visual

Cards are rendered as interlocking chain links — not separate cards with arrows.

Each tool step is a **rounded rectangle card**. Between adjacent cards, a **connector piece** (smaller rounded rectangle) straddles the seam — its top half overlaps the bottom edge of the card above, its bottom half overlaps the top edge of the card below. This creates a visual chain.

The connector piece also serves as the **output wiring UI** — where the user selects which output from the previous step feeds into the next.

### Card Contents

- Tool name
- Per-step agent instruction input field
- Parameter fields (pre-filled from workspace if set)
- Output area (populated after execution with the tool's result)
- X button to remove step
- Drag handle to reorder

### Execution

- **Run button** at the bottom of the chain
- Steps execute sequentially — each step sends a message to the chat agent with the per-step instruction + tool + params
- Agent response (tool result) populates the card's output area
- User reviews output, selects relevant portion/field in the connector, proceeds to next step
- All chain executions are real chat messages — conversation retains full context

### Output Wiring

After a step executes:
1. Output appears in the card
2. User selects a portion/field of the output
3. The connector below shows "Input from: Step N — [selected output]"
4. This feeds into the next step's params or instruction context

---

## 5. Chat States

### Full Chat (Default)

Standard chat experience. Full width center, normal input bar.

### Slim Column

Chat shrinks to sidebar-width column on the right. Messages wrap tightly or truncate. Scrollable. Input bar stays at bottom full-width.

### Input Bar Only

Chat hidden entirely. Input bar at bottom full-width:
- **Input field:** Left side. Serves as chat input or agent instruction depending on mode.
- **Mode toggle:** Small indicator showing "Chat" vs "Agent"
- **Chat popover trigger:** Click target on far right edge. Opens floating chat panel anchored bottom-right (messenger-style). Shows recent message history, scrollable, dismissible.

### Transitions

- Opening a workspace group: Default → Workspace + Chat Column
- Opening chain view: → Workspace + Chain + Input Bar Only
- Closing all workspace groups: reverts to Default
- Layer 3 adds animated transitions for drag-preview states

---

## 6. Component Architecture

### New Components

| Component | Level | Description |
|-----------|-------|-------------|
| `WorkspaceProvider` | Provider | Layout state, active groups, selected tools, chain steps |
| `ToolExplorer` | Organism | Sidebar content: search + group card list |
| `GroupCard` | Molecule | Dual-target card: expand symbol + main click area |
| `ToolWorkspace` | Organism | Center panel: stacked group sections with tool buttons |
| `ToolButton` | Atom | Individual tool button in workspace |
| `ParamTable` | Molecule | Read-only / interactive parameter table |
| `ChainView` | Organism | Right column pipeline builder |
| `ChainCard` | Molecule | Individual chain step card |
| `ChainConnector` | Molecule | Link piece between chain cards (output wiring) |
| `ChatPopover` | Molecule | Messenger-style floating chat panel |

### Retired/Refactored

- `Sidebar.tsx` — content replaced by `ToolExplorer`
- `ToolCategory.tsx` — retired (group cards replace category headers)
- `ToolRow.tsx` — retired (tool buttons in workspace replace checkbox rows)
- `ToolChip.tsx` — may be repurposed for active group indicators

### Provider Hierarchy

```
App
  └─ AuthProvider
      └─ ThemeProvider
          └─ ToolProvider (existing — still manages tool activation state)
              └─ WorkspaceProvider (new — layout, groups, chain)
                  └─ ChatProvider
                      └─ Routes/Pages
```

`WorkspaceProvider` syncs tool activations back to `ToolProvider` so the chat agent knows which tools are available.

---

## 7. Data Flow

### Tool Registry

Static data from `workflow_groups.py` exposed via existing `/api/tools` endpoint. Groups, tool names, descriptions, and parameter schemas all available client-side.

### Tool Activation

1. User opens group in workspace (click or drag-drop)
2. `WorkspaceProvider` adds group to active set
3. Syncs to `ToolProvider` → calls existing tool select/deselect API
4. Agent now has access to those tools

### Chain Execution

1. User builds chain: pushes tools from workspace to chain view
2. Sets per-step instructions and params
3. Clicks Run
4. Each step: `WorkspaceProvider` dispatches a chat message via the existing stream endpoint with instruction + tool context
5. Response populates chain card output
6. User wires output → next step input via connector UI
7. All messages appear in chat history (visible in popover or slim column)

---

## 8. Implementation Layers

### Layer 1 — Sidebar + Workspace + Chat States

**Delivers:** Functional tool browsing and selection. Chat collapses when workspace is open. Users can search, browse groups, view tool details, toggle interactive params, and activate tools for the agent.

- `WorkspaceProvider`
- `ToolExplorer` (search + `GroupCard` list)
- `ToolWorkspace` (stacked group sections + `ToolButton` + `ParamTable`)
- Chat slim column and input-bar-only states
- `ChatPopover`
- Push-to-chain button visible but disabled ("Coming soon")

### Layer 2 — Chain View

**Delivers:** Full tool chaining pipeline.

- `ChainView` (collapsed/expanded)
- `ChainCard` + `ChainConnector` (chain link visual)
- Per-step instruction inputs
- Sequential execution via chat stream
- Output display and output-to-input wiring

### Layer 3 — Drag & Polish

**Delivers:** Drag interactions and animations.

- Drag group cards from sidebar with layout preview zones
- Drop commits layout + activates group
- Drag reorder within sidebar
- Animated transitions between layout states
- Drag reorder chain steps

---

## 9. Visual Style

- Follows existing theme: glass/accent CSS custom properties (`--accent`, `--glass-bg-solid`, `--text-muted`, etc.)
- Group cards use glass background with accent borders when active
- Chain links use accent color for connectors, glass background for cards
- Chat popover matches existing glass aesthetic
- Tool buttons: monospace font, accent highlight when selected
- Transitions: 200-300ms ease-out for layout changes
