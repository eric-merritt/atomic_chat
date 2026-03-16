# React + Tailwind Frontend Refactor — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the inline HTML/JS/CSS in Flask with a React + TypeScript + Tailwind SPA, keeping the Flask backend as a headless API.

**Architecture:** Vite-based React SPA in `frontend/` subdirectory. Dev proxy to Flask. Atomic design with typed data atoms, adapter layer for API, context-based state. Grid layout with animated sidebar via `grid-template-columns` transition.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind CSS, React Router, Vitest + React Testing Library

**Spec:** `docs/superpowers/specs/2026-03-16-react-refactor-design.md`

---

## Chunk 1: Scaffold + Data Atoms

### Task 1: Initialize Vite + React + TypeScript project

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/index.css`

- [ ] **Step 1: Scaffold Vite project**

```bash
cd /home/ermer/devproj/python/agentic_w_langchain_ollama
npm create vite@latest frontend -- --template react-ts
```

- [ ] **Step 2: Install Tailwind + React Router**

```bash
cd frontend
npm install react-router-dom
npm install -D tailwindcss @tailwindcss/vite
```

- [ ] **Step 3: Configure Tailwind**

`frontend/src/index.css`:
```css
@import "tailwindcss";
```

`frontend/vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:5000',
      '/static': 'http://localhost:5000',
    },
  },
})
```

- [ ] **Step 4: Add theme CSS variables to index.css**

Append to `frontend/src/index.css` — all 6 theme definitions from the current `main.css`. Each theme is a `[data-theme="..."]` selector with CSS custom properties:

```css
/* Dark: Obsidian (default) */
[data-theme="obsidian"] {
  --bg-base: #0b0e17;
  --bg-mesh-1: #0d1a2d;
  --bg-mesh-2: #1a0d2e;
  --bg-mesh-3: #0b1a1a;
  --glass-bg: rgba(15, 20, 40, 0.2);
  --glass-bg-solid: rgba(15, 20, 40, 0.2);
  --glass-border: rgba(100, 140, 255, 0.12);
  --glass-highlight: rgba(100, 140, 255, 0.06);
  --text: #e2e6f0;
  --text-secondary: #8890a8;
  --text-muted: #555d78;
  --accent: #6c8cff;
  --accent-glow: rgba(108, 140, 255, 0.3);
  --accent-hover: #8aa4ff;
  --danger: #ff6b6b;
  --success: #6bffa8;
  --input-bg: rgba(8, 12, 28, 0.6);
  --scrollbar-thumb: rgba(100, 140, 255, 0.15);
  --msg-user: rgba(108, 140, 255, 0.12);
  --msg-assistant: rgba(15, 20, 40, 0.5);
  --mode: dark;
}

[data-theme="carbon"] {
  --bg-base: #0a0a0a;
  --bg-mesh-1: #1a1a1a;
  --bg-mesh-2: #0a1a0a;
  --bg-mesh-3: #1a0a0a;
  --glass-bg: rgba(20, 20, 20, 0.2);
  --glass-bg-solid: rgba(20, 20, 20, 0.2);
  --glass-border: rgba(80, 255, 160, 0.12);
  --glass-highlight: rgba(80, 255, 160, 0.04);
  --text: #e0e0e0;
  --text-secondary: #888;
  --text-muted: #555;
  --accent: #50ffa0;
  --accent-glow: rgba(80, 255, 160, 0.25);
  --accent-hover: #70ffb0;
  --danger: #ff5555;
  --success: #50ffa0;
  --input-bg: rgba(5, 5, 5, 0.6);
  --scrollbar-thumb: rgba(80, 255, 160, 0.12);
  --msg-user: rgba(80, 255, 160, 0.08);
  --msg-assistant: rgba(20, 20, 20, 0.5);
  --mode: dark;
}

[data-theme="amethyst"] {
  --bg-base: #100818;
  --bg-mesh-1: #1e0a30;
  --bg-mesh-2: #0a0820;
  --bg-mesh-3: #200a18;
  --glass-bg: rgba(25, 12, 40, 0.2);
  --glass-bg-solid: rgba(25, 12, 40, 0.2);
  --glass-border: rgba(190, 130, 255, 0.12);
  --glass-highlight: rgba(190, 130, 255, 0.05);
  --text: #e8e0f0;
  --text-secondary: #9888b0;
  --text-muted: #605070;
  --accent: #be82ff;
  --accent-glow: rgba(190, 130, 255, 0.3);
  --accent-hover: #d0a0ff;
  --danger: #ff6b8a;
  --success: #82ffbe;
  --input-bg: rgba(12, 6, 24, 0.6);
  --scrollbar-thumb: rgba(190, 130, 255, 0.15);
  --msg-user: rgba(190, 130, 255, 0.1);
  --msg-assistant: rgba(25, 12, 40, 0.5);
  --mode: dark;
}

[data-theme="frost"] {
  --bg-base: #e8edf5;
  --bg-mesh-1: #d0daf0;
  --bg-mesh-2: #e0e8ff;
  --bg-mesh-3: #d5e8f0;
  --glass-bg: rgba(255, 255, 255, 0.2);
  --glass-bg-solid: rgba(255, 255, 255, 0.2);
  --glass-border: rgba(60, 100, 180, 0.15);
  --glass-highlight: rgba(255, 255, 255, 0.5);
  --text: #1a2040;
  --text-secondary: #506080;
  --text-muted: #8898b8;
  --accent: #3b5cff;
  --accent-glow: rgba(59, 92, 255, 0.2);
  --accent-hover: #5070ff;
  --danger: #e04040;
  --success: #20a060;
  --input-bg: rgba(255, 255, 255, 0.5);
  --scrollbar-thumb: rgba(60, 100, 180, 0.2);
  --msg-user: rgba(59, 92, 255, 0.1);
  --msg-assistant: rgba(255, 255, 255, 0.45);
  --mode: light;
}

[data-theme="sand"] {
  --bg-base: #f0ebe0;
  --bg-mesh-1: #e8dcc8;
  --bg-mesh-2: #f0e0d0;
  --bg-mesh-3: #e0d8c8;
  --glass-bg: rgba(255, 252, 245, 0.2);
  --glass-bg-solid: rgba(255, 252, 245, 0.2);
  --glass-border: rgba(160, 120, 60, 0.15);
  --glass-highlight: rgba(255, 255, 255, 0.4);
  --text: #2a2418;
  --text-secondary: #6a5a40;
  --text-muted: #a09070;
  --accent: #c07820;
  --accent-glow: rgba(192, 120, 32, 0.2);
  --accent-hover: #d88a30;
  --danger: #c04030;
  --success: #408030;
  --input-bg: rgba(255, 252, 245, 0.5);
  --scrollbar-thumb: rgba(160, 120, 60, 0.2);
  --msg-user: rgba(192, 120, 32, 0.1);
  --msg-assistant: rgba(255, 252, 245, 0.45);
  --mode: light;
}

[data-theme="blossom"] {
  --bg-base: #f5e8ef;
  --bg-mesh-1: #f0d0e0;
  --bg-mesh-2: #ffe0ea;
  --bg-mesh-3: #e8d0e8;
  --glass-bg: rgba(255, 250, 252, 0.2);
  --glass-bg-solid: rgba(255, 250, 252, 0.2);
  --glass-border: rgba(200, 80, 120, 0.12);
  --glass-highlight: rgba(255, 255, 255, 0.45);
  --text: #301828;
  --text-secondary: #805068;
  --text-muted: #b088a0;
  --accent: #d04878;
  --accent-glow: rgba(208, 72, 120, 0.2);
  --accent-hover: #e06090;
  --danger: #c03030;
  --success: #30a060;
  --input-bg: rgba(255, 250, 252, 0.5);
  --scrollbar-thumb: rgba(200, 80, 120, 0.15);
  --msg-user: rgba(208, 72, 120, 0.1);
  --msg-assistant: rgba(255, 250, 252, 0.45);
  --mode: light;
}
```

- [ ] **Step 5: Minimal App.tsx with theme test**

`frontend/src/App.tsx`:
```tsx
export default function App() {
  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text)]">
      <p>Agentic Chat — React</p>
    </div>
  );
}
```

- [ ] **Step 6: Verify dev server starts**

```bash
cd frontend && npm run dev
```

Expected: Vite dev server on http://localhost:5173, page renders with obsidian theme background.

- [ ] **Step 7: Install Vitest + React Testing Library**

```bash
cd frontend
npm install -D vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
```

Add to `frontend/vite.config.ts` inside `defineConfig`:
```typescript
test: {
  globals: true,
  environment: 'jsdom',
  setupFiles: './src/test-setup.ts',
},
```

Create `frontend/src/test-setup.ts`:
```typescript
import '@testing-library/jest-dom';
```

- [ ] **Step 8: Verify tests run**

```bash
cd frontend && npx vitest run
```

Expected: 0 tests, no errors.

- [ ] **Step 9: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold Vite + React + TypeScript + Tailwind frontend"
```

---

### Task 2: Model atom

**Files:**
- Create: `frontend/src/atoms/model.ts`
- Create: `frontend/src/atoms/__tests__/model.test.ts`

- [ ] **Step 1: Write failing tests**

`frontend/src/atoms/__tests__/model.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';
import { modelId, parseModelString } from '../model';

describe('modelId', () => {
  it('builds id with devTeam', () => {
    expect(modelId({
      devTeam: 'huihui_ai',
      name: 'qwen2.5-coder-abliterate',
      numParams: '14b',
      available: true,
      format: null, maker: null, year: null, description: null,
      goodAt: null, notSoGoodAt: null, idealUseCases: null, contextWindow: null,
    })).toBe('huihui_ai/qwen2.5-coder-abliterate:14b');
  });

  it('builds id without devTeam', () => {
    expect(modelId({
      devTeam: null,
      name: 'llama3.1',
      numParams: '8b',
      available: true,
      format: null, maker: null, year: null, description: null,
      goodAt: null, notSoGoodAt: null, idealUseCases: null, contextWindow: null,
    })).toBe('llama3.1:8b');
  });
});

describe('parseModelString', () => {
  it('parses devTeam/name:params', () => {
    const m = parseModelString('huihui_ai/qwen2.5-coder-abliterate:14b');
    expect(m.devTeam).toBe('huihui_ai');
    expect(m.name).toBe('qwen2.5-coder-abliterate');
    expect(m.numParams).toBe('14b');
    expect(m.available).toBe(true);
  });

  it('parses name:params without devTeam', () => {
    const m = parseModelString('llama3.1:8b');
    expect(m.devTeam).toBeNull();
    expect(m.name).toBe('llama3.1');
    expect(m.numParams).toBe('8b');
  });

  it('sets all metadata to null', () => {
    const m = parseModelString('llama3.1:8b');
    expect(m.format).toBeNull();
    expect(m.maker).toBeNull();
    expect(m.year).toBeNull();
    expect(m.description).toBeNull();
    expect(m.goodAt).toBeNull();
    expect(m.notSoGoodAt).toBeNull();
    expect(m.idealUseCases).toBeNull();
    expect(m.contextWindow).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/atoms/__tests__/model.test.ts
```

Expected: FAIL — cannot find module `../model`

- [ ] **Step 3: Implement model atom**

`frontend/src/atoms/model.ts`:
```typescript
export interface Model {
  devTeam: string | null;
  name: string;
  numParams: string;
  available: boolean;
  format: string | null;
  maker: string | null;
  year: number | null;
  description: string | null;
  goodAt: string[] | null;
  notSoGoodAt: string[] | null;
  idealUseCases: string[] | null;
  contextWindow: number | null;
}

export function modelId(m: Model): string {
  const base = m.devTeam ? `${m.devTeam}/${m.name}` : m.name;
  return `${base}:${m.numParams}`;
}

export function parseModelString(s: string): Model {
  let devTeam: string | null = null;
  let rest = s;

  const slashIdx = s.indexOf('/');
  if (slashIdx !== -1) {
    devTeam = s.slice(0, slashIdx);
    rest = s.slice(slashIdx + 1);
  }

  const colonIdx = rest.lastIndexOf(':');
  const name = colonIdx !== -1 ? rest.slice(0, colonIdx) : rest;
  const numParams = colonIdx !== -1 ? rest.slice(colonIdx + 1) : '';

  return {
    devTeam,
    name,
    numParams,
    available: true,
    format: null,
    maker: null,
    year: null,
    description: null,
    goodAt: null,
    notSoGoodAt: null,
    idealUseCases: null,
    contextWindow: null,
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/atoms/__tests__/model.test.ts
```

Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/atoms/
git commit -m "feat: add Model atom with modelId and parseModelString"
```

---

### Task 3: Tool atom

**Files:**
- Create: `frontend/src/atoms/tool.ts`
- Create: `frontend/src/atoms/__tests__/tool.test.ts`

- [ ] **Step 1: Write failing tests**

`frontend/src/atoms/__tests__/tool.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';
import { buildCategory } from '../tool';
import type { Tool } from '../tool';

const makeTool = (name: string, selected: boolean): Tool => ({
  name,
  description: `desc for ${name}`,
  params: {},
  category: 'Test',
  selected,
});

describe('buildCategory', () => {
  it('computes allSelected when all tools selected', () => {
    const cat = buildCategory('Test', [makeTool('a', true), makeTool('b', true)]);
    expect(cat.allSelected).toBe(true);
    expect(cat.someSelected).toBe(true);
    expect(cat.count).toBe(2);
    expect(cat.selectedCount).toBe(2);
  });

  it('computes someSelected when partially selected', () => {
    const cat = buildCategory('Test', [makeTool('a', true), makeTool('b', false)]);
    expect(cat.allSelected).toBe(false);
    expect(cat.someSelected).toBe(true);
    expect(cat.selectedCount).toBe(1);
  });

  it('computes none selected', () => {
    const cat = buildCategory('Test', [makeTool('a', false), makeTool('b', false)]);
    expect(cat.allSelected).toBe(false);
    expect(cat.someSelected).toBe(false);
    expect(cat.selectedCount).toBe(0);
  });

  it('handles empty tools array', () => {
    const cat = buildCategory('Empty', []);
    expect(cat.count).toBe(0);
    expect(cat.allSelected).toBe(true);
    expect(cat.someSelected).toBe(false);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/atoms/__tests__/tool.test.ts
```

Expected: FAIL

- [ ] **Step 3: Implement tool atom**

`frontend/src/atoms/tool.ts`:
```typescript
export interface ToolParam {
  type: string;
  description: string;
  required: boolean;
  default?: unknown;
}

export interface Tool {
  name: string;
  description: string;
  params: Record<string, ToolParam>;
  category: string;
  selected: boolean;
}

export interface ToolCategory {
  name: string;
  tools: Tool[];
  readonly allSelected: boolean;
  readonly someSelected: boolean;
  readonly count: number;
  readonly selectedCount: number;
}

export function buildCategory(name: string, tools: Tool[]): ToolCategory {
  const count = tools.length;
  const selectedCount = tools.filter((t) => t.selected).length;
  return {
    name,
    tools,
    get allSelected() { return count === 0 || selectedCount === count; },
    get someSelected() { return selectedCount > 0; },
    get count() { return count; },
    get selectedCount() { return selectedCount; },
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/atoms/__tests__/tool.test.ts
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/atoms/tool.ts frontend/src/atoms/__tests__/tool.test.ts
git commit -m "feat: add Tool atom with buildCategory factory"
```

---

### Task 4: Message atom

**Files:**
- Create: `frontend/src/atoms/message.ts`
- Create: `frontend/src/atoms/__tests__/message.test.ts`

- [ ] **Step 1: Write failing tests**

`frontend/src/atoms/__tests__/message.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';
import { createMessage, createMessageFromHistory } from '../message';

describe('createMessage', () => {
  it('creates a user message with generated id', () => {
    const m = createMessage('user', 'hello');
    expect(m.id).toBeTruthy();
    expect(m.role).toBe('user');
    expect(m.content).toBe('hello');
    expect(m.images).toEqual([]);
    expect(m.toolCalls).toEqual([]);
    expect(m.timestamp).toBeGreaterThan(0);
  });

  it('creates an error message', () => {
    const m = createMessage('error', 'something broke');
    expect(m.role).toBe('error');
  });
});

describe('createMessageFromHistory', () => {
  it('constructs Message from backend history entry', () => {
    const m = createMessageFromHistory({ role: 'assistant', content: 'hi' });
    expect(m.id).toBeTruthy();
    expect(m.role).toBe('assistant');
    expect(m.content).toBe('hi');
    expect(m.images).toEqual([]);
    expect(m.toolCalls).toEqual([]);
    expect(m.timestamp).toBe(0);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/atoms/__tests__/message.test.ts
```

Expected: FAIL

- [ ] **Step 3: Implement message atom**

`frontend/src/atoms/message.ts`:
```typescript
export type MessageRole = 'user' | 'assistant' | 'error';

export interface ImageAttachment {
  src: string;
  filename: string;
  sizeKb: number;
}

export interface ToolCallInfo {
  id?: string;
  tool: string;
  input: string;
  params?: Record<string, unknown>;
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  images: ImageAttachment[];
  toolCalls: ToolCallInfo[];
  timestamp: number;
}

let _counter = 0;
function genId(): string {
  return `msg-${Date.now()}-${++_counter}`;
}

export function createMessage(role: MessageRole, content: string): Message {
  return {
    id: genId(),
    role,
    content,
    images: [],
    toolCalls: [],
    timestamp: Date.now(),
  };
}

export function createMessageFromHistory(entry: {
  role: string;
  content: string;
}): Message {
  return {
    id: genId(),
    role: entry.role as MessageRole,
    content: entry.content,
    images: [],
    toolCalls: [],
    timestamp: 0,
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/atoms/__tests__/message.test.ts
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/atoms/message.ts frontend/src/atoms/__tests__/message.test.ts
git commit -m "feat: add Message atom with factory functions"
```

---

### Task 5: Theme atom

**Files:**
- Create: `frontend/src/atoms/theme.ts`
- Create: `frontend/src/atoms/__tests__/theme.test.ts`

- [ ] **Step 1: Write failing tests**

`frontend/src/atoms/__tests__/theme.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';
import { THEMES, getThemeById } from '../theme';

describe('THEMES', () => {
  it('has 6 themes', () => {
    expect(THEMES).toHaveLength(6);
  });

  it('has 3 dark and 3 light', () => {
    expect(THEMES.filter((t) => t.mode === 'dark')).toHaveLength(3);
    expect(THEMES.filter((t) => t.mode === 'light')).toHaveLength(3);
  });
});

describe('getThemeById', () => {
  it('finds obsidian', () => {
    const t = getThemeById('obsidian');
    expect(t?.label).toBe('Obsidian');
    expect(t?.mode).toBe('dark');
  });

  it('returns undefined for unknown id', () => {
    expect(getThemeById('nonexistent')).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/atoms/__tests__/theme.test.ts
```

Expected: FAIL

- [ ] **Step 3: Implement theme atom**

`frontend/src/atoms/theme.ts`:
```typescript
export type ThemeMode = 'dark' | 'light';

export interface Theme {
  id: string;
  label: string;
  mode: ThemeMode;
}

export const THEMES: Theme[] = [
  { id: 'obsidian', label: 'Obsidian', mode: 'dark' },
  { id: 'carbon', label: 'Carbon', mode: 'dark' },
  { id: 'amethyst', label: 'Amethyst', mode: 'dark' },
  { id: 'frost', label: 'Frost', mode: 'light' },
  { id: 'sand', label: 'Sand', mode: 'light' },
  { id: 'blossom', label: 'Blossom', mode: 'light' },
];

export function getThemeById(id: string): Theme | undefined {
  return THEMES.find((t) => t.id === id);
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/atoms/__tests__/theme.test.ts
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/atoms/theme.ts frontend/src/atoms/__tests__/theme.test.ts
git commit -m "feat: add Theme atom with THEMES registry"
```

---

### Task 6: Stream atom

**Files:**
- Create: `frontend/src/atoms/stream.ts`
- Create: `frontend/src/atoms/__tests__/stream.test.ts`

- [ ] **Step 1: Write failing tests**

`frontend/src/atoms/__tests__/stream.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';
import { parseStreamLine } from '../stream';

describe('parseStreamLine', () => {
  it('parses token event', () => {
    const ev = parseStreamLine({ token: 'hello' });
    expect(ev).toEqual({ type: 'token', token: 'hello' });
  });

  it('parses tool_call event', () => {
    const ev = parseStreamLine({ tool_call: { tool: 'web_search', input: 'test' } });
    expect(ev).toEqual({ type: 'tool_call', tool: 'web_search', input: 'test' });
  });

  it('parses tool_result event', () => {
    const ev = parseStreamLine({ tool_result: { tool: 'web_search', output: 'results' } });
    expect(ev).toEqual({ type: 'tool_result', tool: 'web_search', output: 'results' });
  });

  it('parses image event with snake_case to camelCase', () => {
    const ev = parseStreamLine({ image: { src: '/img.jpg', filename: 'img.jpg', size_kb: 42 } });
    expect(ev).toEqual({ type: 'image', src: '/img.jpg', filename: 'img.jpg', sizeKb: 42 });
  });

  it('parses error event', () => {
    const ev = parseStreamLine({ error: 'something broke' });
    expect(ev).toEqual({ type: 'error', message: 'something broke' });
  });

  it('returns null for unknown shape', () => {
    const ev = parseStreamLine({ unknown: true });
    expect(ev).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/atoms/__tests__/stream.test.ts
```

Expected: FAIL

- [ ] **Step 3: Implement stream atom**

`frontend/src/atoms/stream.ts`:
```typescript
export type StreamEvent =
  | { type: 'token'; token: string }
  | { type: 'tool_call'; tool: string; input: string }
  | { type: 'tool_result'; tool: string; output: string }
  | { type: 'image'; src: string; filename: string; sizeKb: number }
  | { type: 'error'; message: string };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function parseStreamLine(raw: any): StreamEvent | null {
  if ('token' in raw) {
    return { type: 'token', token: raw.token };
  }
  if ('tool_call' in raw) {
    return { type: 'tool_call', tool: raw.tool_call.tool, input: raw.tool_call.input };
  }
  if ('tool_result' in raw) {
    return { type: 'tool_result', tool: raw.tool_result.tool, output: raw.tool_result.output };
  }
  if ('image' in raw) {
    return {
      type: 'image',
      src: raw.image.src,
      filename: raw.image.filename,
      sizeKb: raw.image.size_kb,
    };
  }
  if ('error' in raw) {
    return { type: 'error', message: raw.error };
  }
  return null;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/atoms/__tests__/stream.test.ts
```

Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/atoms/stream.ts frontend/src/atoms/__tests__/stream.test.ts
git commit -m "feat: add Stream atom with NDJSON wire format parser"
```

---

### Task 7: Agent and API atoms

**Files:**
- Create: `frontend/src/atoms/agent.ts`
- Create: `frontend/src/atoms/api.ts`

- [ ] **Step 1: Create agent atom**

`frontend/src/atoms/agent.ts`:
```typescript
export type LoopStepKind = 'inference' | 'summarization' | 'definition' | 'execution';

export interface LoopStep {
  kind: LoopStepKind;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  result?: string;
}

export interface Plan {
  id: string;
  steps: LoopStep[];
  createdAt: number;
}
```

- [ ] **Step 2: Create API response atom**

`frontend/src/atoms/api.ts`:
```typescript
export interface ApiResponse<T> {
  data: T;
  error?: string;
}
```

- [ ] **Step 3: Create barrel export**

`frontend/src/atoms/index.ts`:
```typescript
export * from './model';
export * from './tool';
export * from './message';
export * from './theme';
export * from './stream';
export * from './agent';
export * from './api';
```

- [ ] **Step 4: Verify all atom tests pass**

```bash
cd frontend && npx vitest run src/atoms/
```

Expected: All tests PASS (17 total across 5 test files)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/atoms/
git commit -m "feat: add Agent, API atoms and barrel export"
```

---

## Chunk 2: API Adapters

### Task 8: Models adapter

**Files:**
- Create: `frontend/src/api/models.ts`
- Create: `frontend/src/api/__tests__/models.test.ts`

- [ ] **Step 1: Write failing tests**

`frontend/src/api/__tests__/models.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchModels, selectModel } from '../models';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => { mockFetch.mockReset(); });

describe('fetchModels', () => {
  it('parses model strings into Model atoms', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        models: ['huihui_ai/qwen2.5-coder-abliterate:14b', 'llama3.1:8b'],
        current: 'huihui_ai/qwen2.5-coder-abliterate:14b',
      }),
    });

    const result = await fetchModels();
    expect(result.data).toHaveLength(2);
    expect(result.data![0].devTeam).toBe('huihui_ai');
    expect(result.data![0].name).toBe('qwen2.5-coder-abliterate');
    expect(result.data![0].numParams).toBe('14b');
    expect(result.data![1].devTeam).toBeNull();
    expect(result.data![1].name).toBe('llama3.1');
  });

  it('returns error on fetch failure', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 });

    const result = await fetchModels();
    expect(result.error).toBeTruthy();
    expect(result.data).toEqual([]);
  });
});

describe('selectModel', () => {
  it('posts model id to API', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ model: 'llama3.1:8b' }),
    });

    await selectModel({
      devTeam: null, name: 'llama3.1', numParams: '8b', available: true,
      format: null, maker: null, year: null, description: null,
      goodAt: null, notSoGoodAt: null, idealUseCases: null, contextWindow: null,
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/models', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ model: 'llama3.1:8b' }),
    }));
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/api/__tests__/models.test.ts
```

Expected: FAIL

- [ ] **Step 3: Implement models adapter**

`frontend/src/api/models.ts`:
```typescript
import type { Model } from '../atoms/model';
import { parseModelString, modelId } from '../atoms/model';
import type { ApiResponse } from '../atoms/api';

export async function fetchModels(): Promise<ApiResponse<Model[]> & { current: string | null }> {
  try {
    const resp = await fetch('/api/models');
    if (!resp.ok) {
      return { data: [], error: `Failed to fetch models: ${resp.status}`, current: null };
    }
    const json = await resp.json();
    const models = (json.models as string[]).map(parseModelString);
    return { data: models, current: json.current ?? null };
  } catch (e) {
    return { data: [], error: String(e), current: null };
  }
}

export async function selectModel(model: Model): Promise<ApiResponse<string>> {
  const id = modelId(model);
  try {
    const resp = await fetch('/api/models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: id }),
    });
    if (!resp.ok) {
      return { data: '', error: `Failed to select model: ${resp.status}` };
    }
    const json = await resp.json();
    return { data: json.model };
  } catch (e) {
    return { data: '', error: String(e) };
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/api/__tests__/models.test.ts
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/
git commit -m "feat: add models API adapter"
```

---

### Task 9: Tools adapter

**Files:**
- Create: `frontend/src/api/tools.ts`
- Create: `frontend/src/api/__tests__/tools.test.ts`

- [ ] **Step 1: Write failing tests**

`frontend/src/api/__tests__/tools.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchTools, toggleTool, toggleCategory } from '../tools';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => { mockFetch.mockReset(); });

const apiResponse = {
  categories: [
    {
      name: 'Filesystem',
      tools: [
        { name: 'read_file', description: 'Read a file', params: {}, selected: true },
        { name: 'write_file', description: 'Write a file', params: {}, selected: false },
      ],
      all_selected: false,
      some_selected: true,
      count: 2,
      selected_count: 1,
    },
  ],
  selected: ['read_file'],
};

describe('fetchTools', () => {
  it('transforms backend response into ToolCategory atoms', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => apiResponse });

    const result = await fetchTools();
    expect(result.data).toHaveLength(1);
    expect(result.data![0].name).toBe('Filesystem');
    expect(result.data![0].tools).toHaveLength(2);
    expect(result.data![0].tools[0].category).toBe('Filesystem');
    // Derived fields computed client-side
    expect(result.data![0].someSelected).toBe(true);
    expect(result.data![0].allSelected).toBe(false);
    expect(result.data![0].selectedCount).toBe(1);
  });
});

describe('toggleTool', () => {
  it('posts tool name', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => apiResponse });
    await toggleTool('read_file');
    expect(mockFetch).toHaveBeenCalledWith('/api/tools/toggle', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ tool: 'read_file' }),
    }));
  });
});

describe('toggleCategory', () => {
  it('posts category name', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => apiResponse });
    await toggleCategory('Filesystem');
    expect(mockFetch).toHaveBeenCalledWith('/api/tools/toggle_category', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ category: 'Filesystem' }),
    }));
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/api/__tests__/tools.test.ts
```

Expected: FAIL

- [ ] **Step 3: Implement tools adapter**

`frontend/src/api/tools.ts`:
```typescript
import type { Tool, ToolCategory } from '../atoms/tool';
import { buildCategory } from '../atoms/tool';
import type { ApiResponse } from '../atoms/api';

interface RawToolCategory {
  name: string;
  tools: Array<{
    name: string;
    description: string;
    params: Record<string, any>;
    selected: boolean;
  }>;
}

function transformCategories(raw: RawToolCategory[]): ToolCategory[] {
  return raw.map((rc) => {
    const tools: Tool[] = rc.tools.map((t) => ({
      name: t.name,
      description: t.description,
      params: t.params,
      category: rc.name,
      selected: t.selected,
    }));
    return buildCategory(rc.name, tools);
  });
}

async function fetchAndTransform(resp: Response): Promise<ApiResponse<ToolCategory[]>> {
  if (!resp.ok) {
    return { data: [], error: `Failed: ${resp.status}` };
  }
  const json = await resp.json();
  return { data: transformCategories(json.categories) };
}

export async function fetchTools(): Promise<ApiResponse<ToolCategory[]>> {
  try {
    const resp = await fetch('/api/tools');
    return fetchAndTransform(resp);
  } catch (e) {
    return { data: [], error: String(e) };
  }
}

export async function toggleTool(name: string): Promise<ApiResponse<ToolCategory[]>> {
  try {
    const resp = await fetch('/api/tools/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool: name }),
    });
    return fetchAndTransform(resp);
  } catch (e) {
    return { data: [], error: String(e) };
  }
}

export async function toggleCategory(name: string): Promise<ApiResponse<ToolCategory[]>> {
  try {
    const resp = await fetch('/api/tools/toggle_category', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category: name }),
    });
    return fetchAndTransform(resp);
  } catch (e) {
    return { data: [], error: String(e) };
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/api/__tests__/tools.test.ts
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/tools.ts frontend/src/api/__tests__/tools.test.ts
git commit -m "feat: add tools API adapter"
```

---

### Task 10: Chat, history, and system adapters

**Files:**
- Create: `frontend/src/api/chat.ts`
- Create: `frontend/src/api/history.ts`
- Create: `frontend/src/api/system.ts`
- Create: `frontend/src/api/__tests__/chat.test.ts`
- Create: `frontend/src/api/__tests__/history.test.ts`

- [ ] **Step 1: Write failing chat adapter tests**

`frontend/src/api/__tests__/chat.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { cancelChat } from '../chat';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => { mockFetch.mockReset(); });

describe('cancelChat', () => {
  it('posts to cancel endpoint', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    await cancelChat();
    expect(mockFetch).toHaveBeenCalledWith('/api/chat/cancel', { method: 'POST' });
  });
});
```

- [ ] **Step 2: Write failing history adapter tests**

`frontend/src/api/__tests__/history.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchHistory, clearHistory } from '../history';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => { mockFetch.mockReset(); });

describe('fetchHistory', () => {
  it('transforms history entries into Message atoms', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        history: [
          { role: 'user', content: 'hello' },
          { role: 'assistant', content: 'hi' },
        ],
      }),
    });
    const result = await fetchHistory();
    expect(result.data).toHaveLength(2);
    expect(result.data![0].role).toBe('user');
    expect(result.data![0].id).toBeTruthy();
    expect(result.data![0].images).toEqual([]);
    expect(result.data![0].toolCalls).toEqual([]);
    expect(result.data![0].timestamp).toBe(0);
  });
});

describe('clearHistory', () => {
  it('sends DELETE request', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ cleared: true }) });
    await clearHistory();
    expect(mockFetch).toHaveBeenCalledWith('/api/history', { method: 'DELETE' });
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/api/__tests__/
```

Expected: FAIL

- [ ] **Step 4: Implement chat adapter**

`frontend/src/api/chat.ts`:
```typescript
export async function streamChatAsync(message: string): Promise<{
  reader: ReadableStreamDefaultReader<Uint8Array>;
  abort: () => void;
}> {
  const controller = new AbortController();
  const resp = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
    signal: controller.signal,
  });
  if (!resp.ok || !resp.body) throw new Error(`Stream failed: ${resp.status}`);
  return {
    reader: resp.body.getReader(),
    abort: () => controller.abort(),
  };
}

export async function cancelChat(): Promise<void> {
  await fetch('/api/chat/cancel', { method: 'POST' });
}
```

- [ ] **Step 5: Implement history adapter**

`frontend/src/api/history.ts`:
```typescript
import type { Message } from '../atoms/message';
import { createMessageFromHistory } from '../atoms/message';
import type { ApiResponse } from '../atoms/api';

export async function fetchHistory(): Promise<ApiResponse<Message[]>> {
  try {
    const resp = await fetch('/api/history');
    if (!resp.ok) {
      return { data: [], error: `Failed: ${resp.status}` };
    }
    const json = await resp.json();
    const messages = (json.history as Array<{ role: string; content: string }>)
      .map(createMessageFromHistory);
    return { data: messages };
  } catch (e) {
    return { data: [], error: String(e) };
  }
}

export async function clearHistory(): Promise<void> {
  await fetch('/api/history', { method: 'DELETE' });
}
```

- [ ] **Step 6: Implement system adapter**

`frontend/src/api/system.ts`:
```typescript
import type { ApiResponse } from '../atoms/api';

export async function fetchSystemPrompt(): Promise<ApiResponse<string>> {
  try {
    const resp = await fetch('/api/system');
    if (!resp.ok) return { data: '', error: `Failed: ${resp.status}` };
    const json = await resp.json();
    return { data: json.system_prompt };
  } catch (e) {
    return { data: '', error: String(e) };
  }
}

export async function setSystemPrompt(prompt: string): Promise<ApiResponse<string>> {
  try {
    const resp = await fetch('/api/system', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ system_prompt: prompt }),
    });
    if (!resp.ok) return { data: '', error: `Failed: ${resp.status}` };
    const json = await resp.json();
    return { data: json.system_prompt };
  } catch (e) {
    return { data: '', error: String(e) };
  }
}
```

- [ ] **Step 7: Create API barrel export**

`frontend/src/api/index.ts`:
```typescript
export * from './models';
export * from './tools';
export * from './chat';
export * from './history';
export * from './system';
```

- [ ] **Step 8: Run all adapter tests**

```bash
cd frontend && npx vitest run src/api/
```

Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add frontend/src/api/
git commit -m "feat: add chat, history, and system API adapters"
```

---

---

### CHECKPOINT: Chunk 2 complete

**Verify:** `cd frontend && npx vitest run` — all atom + adapter tests pass (~25 tests).

At this point you have: typed data atoms with pure logic, and adapters that transform Flask JSON into those atoms. Nothing renders yet. The next chunk wires these into React state.

**Dependency flow so far:**
```
Chunk 1 (scaffold + atoms) ← Chunk 2 (adapters import atoms)
```

---

## Chunk 3: Hooks + Providers

**Depends on:** Chunk 2 (adapters). Hooks call adapters, adapters return atoms.

This chunk takes the pile of standalone types and adapters and wires them into live React state. After this chunk, every piece of data in the app has a single owner, a single source of truth, and a clean API for components to consume. No UI yet — just the nervous system.

**Build order within this chunk:** Theme → Models → Tools → Stream → Chat → WebSocket. Each builds on the previous: Chat consumes Models and Tools context, Stream is internal to Chat, WebSocket extends Chat for remote mode.

### Task 11: useTheme hook + ThemeProvider

**Depends on:** Theme atom (Task 5)

**Files:**
- Create: `frontend/src/hooks/useTheme.ts`
- Create: `frontend/src/providers/ThemeProvider.tsx`
- Create: `frontend/src/hooks/__tests__/useTheme.test.ts`

- [ ] **Step 1: Write failing tests**

`frontend/src/hooks/__tests__/useTheme.test.ts`:
```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { ThemeProvider } from '../../providers/ThemeProvider';
import { useTheme } from '../useTheme';
import type { ReactNode } from 'react';

const wrapper = ({ children }: { children: ReactNode }) => (
  <ThemeProvider>{children}</ThemeProvider>
);

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});

describe('useTheme', () => {
  it('defaults to obsidian', () => {
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.theme.id).toBe('obsidian');
  });

  it('sets data-theme attribute on html element', () => {
    renderHook(() => useTheme(), { wrapper });
    expect(document.documentElement.getAttribute('data-theme')).toBe('obsidian');
  });

  it('changes theme and persists to localStorage', () => {
    const { result } = renderHook(() => useTheme(), { wrapper });
    act(() => { result.current.setTheme('carbon'); });
    expect(result.current.theme.id).toBe('carbon');
    expect(localStorage.getItem('agentic-theme')).toBe('carbon');
    expect(document.documentElement.getAttribute('data-theme')).toBe('carbon');
  });

  it('restores theme from localStorage', () => {
    localStorage.setItem('agentic-theme', 'frost');
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.theme.id).toBe('frost');
  });

  it('exposes all 6 themes', () => {
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.themes).toHaveLength(6);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useTheme.test.ts
```

Expected: FAIL

- [ ] **Step 3: Implement ThemeProvider and useTheme**

`frontend/src/providers/ThemeProvider.tsx`:
```tsx
import { createContext, useState, useEffect, type ReactNode } from 'react';
import { THEMES, getThemeById, type Theme } from '../atoms/theme';

interface ThemeContextValue {
  theme: Theme;
  setTheme: (id: string) => void;
  themes: Theme[];
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

const STORAGE_KEY = 'agentic-theme';
const DEFAULT_THEME = THEMES[0]; // obsidian

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return (saved && getThemeById(saved)) || DEFAULT_THEME;
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme.id);
  }, [theme]);

  const setTheme = (id: string) => {
    const t = getThemeById(id);
    if (t) {
      setThemeState(t);
      localStorage.setItem(STORAGE_KEY, id);
    }
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme, themes: THEMES }}>
      {children}
    </ThemeContext.Provider>
  );
}
```

`frontend/src/hooks/useTheme.ts`:
```typescript
import { useContext } from 'react';
import { ThemeContext } from '../providers/ThemeProvider';

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useTheme.test.ts
```

Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useTheme.ts frontend/src/providers/ThemeProvider.tsx frontend/src/hooks/__tests__/useTheme.test.ts
git commit -m "feat: add useTheme hook + ThemeProvider"
```

---

### Task 12: useModels hook + ModelProvider

**Depends on:** Model atom (Task 2), models adapter (Task 8)

**Files:**
- Create: `frontend/src/hooks/useModels.ts`
- Create: `frontend/src/providers/ModelProvider.tsx`
- Create: `frontend/src/hooks/__tests__/useModels.test.ts`

- [ ] **Step 1: Write failing tests**

`frontend/src/hooks/__tests__/useModels.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { ModelProvider } from '../../providers/ModelProvider';
import { useModels } from '../useModels';
import type { ReactNode } from 'react';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

const wrapper = ({ children }: { children: ReactNode }) => (
  <ModelProvider>{children}</ModelProvider>
);

const modelsResponse = {
  models: ['huihui_ai/qwen2.5-coder-abliterate:14b', 'llama3.1:8b'],
  current: 'huihui_ai/qwen2.5-coder-abliterate:14b',
};

beforeEach(() => { mockFetch.mockReset(); });

describe('useModels', () => {
  it('fetches models on mount', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => modelsResponse });
    const { result } = renderHook(() => useModels(), { wrapper });

    await waitFor(() => {
      expect(result.current.models).toHaveLength(2);
    });
    expect(result.current.current?.name).toBe('qwen2.5-coder-abliterate');
  });

  it('selects a model', async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => modelsResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ model: 'llama3.1:8b' }) });

    const { result } = renderHook(() => useModels(), { wrapper });

    await waitFor(() => { expect(result.current.models).toHaveLength(2); });

    await act(async () => {
      await result.current.selectModel(result.current.models[1]);
    });

    expect(result.current.current?.name).toBe('llama3.1');
  });

  it('starts with loading true', () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => modelsResponse });
    const { result } = renderHook(() => useModels(), { wrapper });
    expect(result.current.loading).toBe(true);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useModels.test.ts
```

Expected: FAIL

- [ ] **Step 3: Implement ModelProvider and useModels**

`frontend/src/providers/ModelProvider.tsx`:
```tsx
import { createContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { Model } from '../atoms/model';
import { modelId } from '../atoms/model';
import { fetchModels as apiFetchModels, selectModel as apiSelectModel } from '../api/models';

interface ModelContextValue {
  models: Model[];
  current: Model | null;
  selectModel: (model: Model) => Promise<void>;
  loading: boolean;
}

export const ModelContext = createContext<ModelContextValue | null>(null);

export function ModelProvider({ children }: { children: ReactNode }) {
  const [models, setModels] = useState<Model[]>([]);
  const [current, setCurrent] = useState<Model | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetchModels().then((result) => {
      setModels(result.data);
      if (result.current) {
        const match = result.data.find(
          (m) => modelId(m) === result.current
        );
        setCurrent(match ?? null);
      }
      setLoading(false);
    });
  }, []);

  const selectModel = useCallback(async (model: Model) => {
    await apiSelectModel(model);
    setCurrent(model);
  }, []);

  return (
    <ModelContext.Provider value={{ models, current, selectModel, loading }}>
      {children}
    </ModelContext.Provider>
  );
}
```

`frontend/src/hooks/useModels.ts`:
```typescript
import { useContext } from 'react';
import { ModelContext } from '../providers/ModelProvider';

export function useModels() {
  const ctx = useContext(ModelContext);
  if (!ctx) throw new Error('useModels must be used within ModelProvider');
  return ctx;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useModels.test.ts
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useModels.ts frontend/src/providers/ModelProvider.tsx frontend/src/hooks/__tests__/useModels.test.ts
git commit -m "feat: add useModels hook + ModelProvider"
```

---

### Task 13: useTools hook + ToolProvider

**Depends on:** Tool atom (Task 3), tools adapter (Task 9)

**Files:**
- Create: `frontend/src/hooks/useTools.ts`
- Create: `frontend/src/providers/ToolProvider.tsx`
- Create: `frontend/src/hooks/__tests__/useTools.test.ts`

- [ ] **Step 1: Write failing tests**

`frontend/src/hooks/__tests__/useTools.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { ToolProvider } from '../../providers/ToolProvider';
import { useTools } from '../useTools';
import type { ReactNode } from 'react';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

const wrapper = ({ children }: { children: ReactNode }) => (
  <ToolProvider>{children}</ToolProvider>
);

const toolsResponse = {
  categories: [{
    name: 'Web',
    tools: [
      { name: 'web_search', description: 'Search', params: {}, selected: true },
      { name: 'fetch_url', description: 'Fetch', params: {}, selected: false },
    ],
  }],
  selected: ['web_search'],
};

beforeEach(() => { mockFetch.mockReset(); });

describe('useTools', () => {
  it('fetches categories on mount', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => toolsResponse });
    const { result } = renderHook(() => useTools(), { wrapper });
    await waitFor(() => { expect(result.current.categories).toHaveLength(1); });
    expect(result.current.selected).toEqual(['web_search']);
  });

  it('toggles a tool', async () => {
    const toggledResponse = {
      ...toolsResponse,
      categories: [{
        ...toolsResponse.categories[0],
        tools: toolsResponse.categories[0].tools.map((t) =>
          t.name === 'fetch_url' ? { ...t, selected: true } : t
        ),
      }],
      selected: ['web_search', 'fetch_url'],
    };
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => toolsResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => toggledResponse });

    const { result } = renderHook(() => useTools(), { wrapper });
    await waitFor(() => { expect(result.current.categories).toHaveLength(1); });
    await act(async () => { await result.current.toggleTool('fetch_url'); });
    expect(result.current.selected).toEqual(['web_search', 'fetch_url']);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useTools.test.ts
```

Expected: FAIL

- [ ] **Step 3: Implement ToolProvider and useTools**

`frontend/src/providers/ToolProvider.tsx`:
```tsx
import { createContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { ToolCategory } from '../atoms/tool';
import {
  fetchTools as apiFetchTools,
  toggleTool as apiToggleTool,
  toggleCategory as apiToggleCategory,
} from '../api/tools';

interface ToolContextValue {
  categories: ToolCategory[];
  selected: string[];
  toggleTool: (name: string) => Promise<void>;
  toggleCategory: (name: string) => Promise<void>;
}

export const ToolContext = createContext<ToolContextValue | null>(null);

function getSelected(categories: ToolCategory[]): string[] {
  return categories.flatMap((c) => c.tools.filter((t) => t.selected).map((t) => t.name));
}

export function ToolProvider({ children }: { children: ReactNode }) {
  const [categories, setCategories] = useState<ToolCategory[]>([]);

  useEffect(() => {
    apiFetchTools().then((r) => { if (r.data) setCategories(r.data); });
  }, []);

  const toggleTool = useCallback(async (name: string) => {
    const r = await apiToggleTool(name);
    if (r.data) setCategories(r.data);
  }, []);

  const toggleCategory = useCallback(async (name: string) => {
    const r = await apiToggleCategory(name);
    if (r.data) setCategories(r.data);
  }, []);

  return (
    <ToolContext.Provider value={{
      categories,
      selected: getSelected(categories),
      toggleTool,
      toggleCategory,
    }}>
      {children}
    </ToolContext.Provider>
  );
}
```

`frontend/src/hooks/useTools.ts`:
```typescript
import { useContext } from 'react';
import { ToolContext } from '../providers/ToolProvider';

export function useTools() {
  const ctx = useContext(ToolContext);
  if (!ctx) throw new Error('useTools must be used within ToolProvider');
  return ctx;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useTools.test.ts
```

Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useTools.ts frontend/src/providers/ToolProvider.tsx frontend/src/hooks/__tests__/useTools.test.ts
git commit -m "feat: add useTools hook + ToolProvider"
```

---

### Task 14: useStream hook

**Depends on:** Stream atom (Task 6), chat adapter (Task 10)

This is an internal hook — not exposed via context. It's consumed only by `useChat`. It handles the NDJSON ReadableStream parsing loop.

**Files:**
- Create: `frontend/src/hooks/useStream.ts`
- Create: `frontend/src/hooks/__tests__/useStream.test.ts`

- [ ] **Step 1: Write failing tests**

`frontend/src/hooks/__tests__/useStream.test.ts`:
```typescript
import { describe, it, expect, vi } from 'vitest';
import { parseNdjsonLines } from '../useStream';

describe('parseNdjsonLines', () => {
  it('splits complete lines and returns remainder', () => {
    const { events, remainder } = parseNdjsonLines('{"token":"a"}\n{"token":"b"}\n');
    expect(events).toHaveLength(2);
    expect(events[0]).toEqual({ type: 'token', token: 'a' });
    expect(events[1]).toEqual({ type: 'token', token: 'b' });
    expect(remainder).toBe('');
  });

  it('buffers incomplete line', () => {
    const { events, remainder } = parseNdjsonLines('{"token":"a"}\n{"tok');
    expect(events).toHaveLength(1);
    expect(remainder).toBe('{"tok');
  });

  it('handles empty string', () => {
    const { events, remainder } = parseNdjsonLines('');
    expect(events).toHaveLength(0);
    expect(remainder).toBe('');
  });

  it('skips empty lines', () => {
    const { events, remainder } = parseNdjsonLines('\n\n{"token":"a"}\n\n');
    expect(events).toHaveLength(1);
    expect(remainder).toBe('');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useStream.test.ts
```

Expected: FAIL

- [ ] **Step 3: Implement useStream**

`frontend/src/hooks/useStream.ts`:
```typescript
import { useRef, useCallback } from 'react';
import { parseStreamLine, type StreamEvent } from '../atoms/stream';
import { streamChatAsync } from '../api/chat';

export function parseNdjsonLines(text: string): {
  events: StreamEvent[];
  remainder: string;
} {
  const lines = text.split('\n');
  const remainder = lines.pop() ?? '';
  const events: StreamEvent[] = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const raw = JSON.parse(trimmed);
      const ev = parseStreamLine(raw);
      if (ev) events.push(ev);
    } catch {
      // skip malformed lines
    }
  }

  return { events, remainder };
}

export interface StreamCallbacks {
  onEvent: (event: StreamEvent) => void;
  onDone: () => void;
  onError: (error: string) => void;
}

export function useStream() {
  const abortRef = useRef<(() => void) | null>(null);

  const start = useCallback(async (message: string, callbacks: StreamCallbacks) => {
    try {
      const { reader, abort } = await streamChatAsync(message);
      abortRef.current = abort;

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const { events, remainder } = parseNdjsonLines(buffer);
        buffer = remainder;

        for (const ev of events) {
          callbacks.onEvent(ev);
        }
      }

      // Flush remaining buffer
      if (buffer.trim()) {
        const { events } = parseNdjsonLines(buffer + '\n');
        for (const ev of events) {
          callbacks.onEvent(ev);
        }
      }

      callbacks.onDone();
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        callbacks.onError(String(e));
      }
    } finally {
      abortRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.();
  }, []);

  return { start, stop };
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useStream.test.ts
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useStream.ts frontend/src/hooks/__tests__/useStream.test.ts
git commit -m "feat: add useStream hook with NDJSON line parser"
```

---

### Task 15: useChat hook + ChatProvider

**Depends on:** useStream (Task 14), useModels (Task 12), Message atom (Task 4), history adapter (Task 10)

This is the core hook. It consumes the stream hook internally, manages the message list, and listens for model changes to clear history.

**Files:**
- Create: `frontend/src/hooks/useChat.ts`
- Create: `frontend/src/providers/ChatProvider.tsx`
- Create: `frontend/src/hooks/__tests__/useChat.test.ts`

- [ ] **Step 1: Write failing tests**

`frontend/src/hooks/__tests__/useChat.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { ChatProvider } from '../../providers/ChatProvider';
import { ModelProvider } from '../../providers/ModelProvider';
import { useChat } from '../useChat';
import type { ReactNode } from 'react';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => { mockFetch.mockReset(); });

const wrapper = ({ children }: { children: ReactNode }) => (
  <ModelProvider>
    <ChatProvider>{children}</ChatProvider>
  </ModelProvider>
);

describe('useChat', () => {
  it('starts with empty messages and not streaming', async () => {
    // ModelProvider fetches models on mount
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ models: [], current: null }),
    });

    const { result } = renderHook(() => useChat(), { wrapper });

    await waitFor(() => {
      expect(result.current.messages).toEqual([]);
      expect(result.current.streaming).toBe(false);
    });
  });

  it('clearHistory empties messages and calls API', async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => ({ models: [], current: null }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ cleared: true }) });

    const { result } = renderHook(() => useChat(), { wrapper });

    await act(async () => {
      await result.current.clearHistory();
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/history', { method: 'DELETE' });
    expect(result.current.messages).toEqual([]);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useChat.test.ts
```

Expected: FAIL

- [ ] **Step 3: Implement ChatProvider and useChat**

`frontend/src/providers/ChatProvider.tsx`:
```tsx
import {
  createContext,
  useState,
  useCallback,
  useRef,
  useEffect,
  type ReactNode,
} from 'react';
import type { Message } from '../atoms/message';
import { createMessage } from '../atoms/message';
import { cancelChat } from '../api/chat';
import { clearHistory as apiClearHistory } from '../api/history';
import { useStream } from '../hooks/useStream';
import { useModels } from '../hooks/useModels';

interface ChatContextValue {
  messages: Message[];
  sendMessage: (text: string) => void;
  cancelStream: () => void;
  clearHistory: () => Promise<void>;
  streaming: boolean;
}

export const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const { start, stop } = useStream();
  const { current: currentModel } = useModels();
  const prevModelRef = useRef(currentModel);

  // Clear messages when model changes (backend resets history)
  useEffect(() => {
    if (prevModelRef.current && currentModel && prevModelRef.current !== currentModel) {
      setMessages([]);
    }
    prevModelRef.current = currentModel;
  }, [currentModel]);

  const sendMessage = useCallback((text: string) => {
    const userMsg = createMessage('user', text);
    setMessages((prev) => [...prev, userMsg]);
    setStreaming(true);

    let assistantCreated = false;

    start(text, {
      onEvent: (ev) => {
        switch (ev.type) {
          case 'token':
            setMessages((prev) => {
              if (!assistantCreated) {
                // Create the assistant message on first token
                assistantCreated = true;
                return [...prev, createMessage('assistant', ev.token)];
              }
              // Update the last (assistant) message with appended token
              const last = prev[prev.length - 1];
              return [
                ...prev.slice(0, -1),
                { ...last, content: last.content + ev.token },
              ];
            });
            break;
          case 'image':
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last?.role === 'assistant') {
                return [
                  ...prev.slice(0, -1),
                  { ...last, images: [...last.images, { src: ev.src, filename: ev.filename, sizeKb: ev.sizeKb }] },
                ];
              }
              return prev;
            });
            break;
          case 'error':
            setMessages((prev) => [...prev, createMessage('error', ev.message)]);
            break;
        }
      },
      onDone: () => {
        setStreaming(false);
      },
      onError: (error) => {
        setMessages((prev) => [...prev, createMessage('error', error)]);
        setStreaming(false);
      },
    });
  }, [start]);

  const cancelStream = useCallback(() => {
    stop();
    cancelChat();
    setStreaming(false);
  }, [stop]);

  const clearHistory = useCallback(async () => {
    await apiClearHistory();
    setMessages([]);
  }, []);

  return (
    <ChatContext.Provider value={{ messages, sendMessage, cancelStream, clearHistory, streaming }}>
      {children}
    </ChatContext.Provider>
  );
}
```

`frontend/src/hooks/useChat.ts`:
```typescript
import { useContext } from 'react';
import { ChatContext } from '../providers/ChatProvider';

export function useChat() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChat must be used within ChatProvider');
  return ctx;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useChat.test.ts
```

Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useChat.ts frontend/src/providers/ChatProvider.tsx frontend/src/hooks/__tests__/useChat.test.ts
git commit -m "feat: add useChat hook + ChatProvider with streaming"
```

---

### Task 16: useWebSocket hook + WebSocketProvider

**Depends on:** Message atom (Task 4)

**Files:**
- Create: `frontend/src/hooks/useWebSocket.ts`
- Create: `frontend/src/providers/WebSocketProvider.tsx`

- [ ] **Step 1: Implement WebSocketProvider**

`frontend/src/providers/WebSocketProvider.tsx`:
```tsx
import { createContext, useState, useRef, useCallback, useEffect, type ReactNode } from 'react';

interface WebSocketContextValue {
  connected: boolean;
  sendToolResult: (id: string, output: string) => void;
}

export const WebSocketContext = createContext<WebSocketContextValue | null>(null);

interface WebSocketProviderProps {
  children: ReactNode;
  enabled: boolean;
  url?: string;
}

export function WebSocketProvider({
  children,
  enabled,
  url = '/api/chat/ws',
}: WebSocketProviderProps) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}${url}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);

    wsRef.current = ws;

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [enabled, url]);

  const sendToolResult = useCallback((id: string, output: string) => {
    wsRef.current?.send(JSON.stringify({ tool_result: { id, output } }));
  }, []);

  return (
    <WebSocketContext.Provider value={{ connected, sendToolResult }}>
      {children}
    </WebSocketContext.Provider>
  );
}
```

`frontend/src/hooks/useWebSocket.ts`:
```typescript
import { useContext } from 'react';
import { WebSocketContext } from '../providers/WebSocketProvider';

export function useWebSocket() {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error('useWebSocket must be used within WebSocketProvider');
  return ctx;
}
```

- [ ] **Step 2: Write tests for WebSocketProvider**

`frontend/src/hooks/__tests__/useWebSocket.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { ReactNode } from 'react';
import { WebSocketProvider } from '../../providers/WebSocketProvider';
import { useWebSocket } from '../useWebSocket';

// Mock WebSocket
class MockWebSocket {
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  close = vi.fn();
  send(data: string) { this.sent.push(data); }
}

let mockWs: MockWebSocket;

beforeEach(() => {
  mockWs = new MockWebSocket();
  vi.stubGlobal('WebSocket', vi.fn(() => mockWs));
});

function wrapper({ children }: { children: ReactNode }) {
  return <WebSocketProvider enabled={true}>{children}</WebSocketProvider>;
}

describe('useWebSocket', () => {
  it('connects and sets connected=true on open', () => {
    const { result } = renderHook(() => useWebSocket(), { wrapper });
    expect(result.current.connected).toBe(false);
    act(() => { mockWs.onopen?.(); });
    expect(result.current.connected).toBe(true);
  });

  it('sendToolResult sends correct JSON', () => {
    const { result } = renderHook(() => useWebSocket(), { wrapper });
    act(() => { mockWs.onopen?.(); });
    act(() => { result.current.sendToolResult('tool-1', 'done'); });
    expect(mockWs.sent[0]).toBe(JSON.stringify({ tool_result: { id: 'tool-1', output: 'done' } }));
  });

  it('calls ws.close on unmount', () => {
    const { unmount } = renderHook(() => useWebSocket(), { wrapper });
    unmount();
    expect(mockWs.close).toHaveBeenCalled();
  });
});
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useWebSocket.test.ts
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useWebSocket.ts frontend/src/providers/WebSocketProvider.tsx frontend/src/hooks/__tests__/useWebSocket.test.ts
git commit -m "feat: add useWebSocket hook + WebSocketProvider with tests"
```

---

### Task 17: Wire providers into App.tsx

**Depends on:** All providers (Tasks 11-16)

This task connects the provider hierarchy so the entire app has access to state.

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Update App.tsx with nested providers**

`frontend/src/App.tsx`:
```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from './providers/ThemeProvider';
import { ModelProvider } from './providers/ModelProvider';
import { ToolProvider } from './providers/ToolProvider';
import { ChatProvider } from './providers/ChatProvider';
import { WebSocketProvider } from './providers/WebSocketProvider';

function ChatPage() {
  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text)]">
      <p>Agentic Chat — providers wired</p>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <ModelProvider>
          <ToolProvider>
            <ChatProvider>
              <WebSocketProvider enabled={false}>
                <Routes>
                  <Route path="/" element={<ChatPage />} />
                </Routes>
              </WebSocketProvider>
            </ChatProvider>
          </ToolProvider>
        </ModelProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
```

- [ ] **Step 2: Verify dev server starts with providers**

```bash
cd frontend && npm run dev
```

Expected: Page renders, no console errors. Theme applied. (Models/tools fetch will fail without Flask running — that's expected.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: wire provider hierarchy into App.tsx"
```

---

### CHECKPOINT: Chunk 3 complete

**Verify:** `cd frontend && npx vitest run` — all tests pass (~40 tests across atoms, adapters, hooks).

At this point: every piece of app state has a typed owner. Components can `useTheme()`, `useModels()`, `useTools()`, `useChat()` and get fully typed data back. The nervous system is live — now we build the body.

**Dependency flow:**
```
Chunk 1 (atoms) ← Chunk 2 (adapters) ← Chunk 3 (hooks/providers)
```

---

## Chunk 4: UI Atom Components

**Depends on:** Chunk 1 (atoms for types), Chunk 3 (hooks for context — but UI atoms don't use hooks; they're purely presentational). This chunk can be built in any order relative to Chunk 3, but it's cleaner after hooks exist so molecules (Chunk 5) can immediately use them.

These are the smallest visual building blocks. Zero business logic. Every component here is a leaf node — it accepts props and renders styled markup.

### Task 18: Button component

**Files:**
- Create: `frontend/src/components/atoms/Button.tsx`
- Create: `frontend/src/components/atoms/__tests__/Button.test.tsx`

- [ ] **Step 1: Write failing test**

`frontend/src/components/atoms/__tests__/Button.test.tsx`:
```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button } from '../Button';

describe('Button', () => {
  it('renders with label', () => {
    render(<Button variant="primary" onClick={() => {}}>Send</Button>);
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
  });

  it('calls onClick', async () => {
    const fn = vi.fn();
    render(<Button variant="primary" onClick={fn}>Click</Button>);
    await userEvent.click(screen.getByRole('button'));
    expect(fn).toHaveBeenCalledOnce();
  });

  it('is disabled when disabled prop is true', () => {
    render(<Button variant="primary" onClick={() => {}} disabled>Send</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('applies variant classes', () => {
    const { container } = render(<Button variant="danger" onClick={() => {}}>Del</Button>);
    expect(container.firstChild).toHaveClass('bg-[var(--danger)]');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/atoms/__tests__/Button.test.tsx
```

Expected: FAIL

- [ ] **Step 3: Implement Button**

`frontend/src/components/atoms/Button.tsx`:
```tsx
import type { ButtonHTMLAttributes, ReactNode } from 'react';

type ButtonVariant = 'primary' | 'ghost' | 'danger';

const variantClasses: Record<ButtonVariant, string> = {
  primary: 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] disabled:opacity-30',
  ghost: 'bg-transparent border border-[var(--glass-border)] text-[var(--text-secondary)] hover:bg-[var(--glass-highlight)]',
  danger: 'bg-[var(--danger)] text-white hover:brightness-110',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant: ButtonVariant;
  children: ReactNode;
}

export function Button({ variant, children, className = '', ...props }: ButtonProps) {
  return (
    <button
      className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all cursor-pointer ${variantClasses[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend && npx vitest run src/components/atoms/__tests__/Button.test.tsx
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/atoms/Button.tsx frontend/src/components/atoms/__tests__/Button.test.tsx
git commit -m "feat: add Button UI atom"
```

---

### Task 19: Remaining UI atoms (Input, Select, Badge, Icon, Checkbox, StatusText, Dot)

**Files:**
- Create: `frontend/src/components/atoms/Input.tsx`
- Create: `frontend/src/components/atoms/Select.tsx`
- Create: `frontend/src/components/atoms/Badge.tsx`
- Create: `frontend/src/components/atoms/Icon.tsx`
- Create: `frontend/src/components/atoms/Checkbox.tsx`
- Create: `frontend/src/components/atoms/StatusText.tsx`
- Create: `frontend/src/components/atoms/Dot.tsx`
- Create: `frontend/src/components/atoms/index.ts`
- Create: `frontend/src/components/atoms/__tests__/atoms.test.tsx`

- [ ] **Step 1: Write failing tests for all remaining atoms**

`frontend/src/components/atoms/__tests__/atoms.test.tsx`:
```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Input } from '../Input';
import { Select } from '../Select';
import { Badge } from '../Badge';
import { Icon } from '../Icon';
import { Checkbox } from '../Checkbox';
import { StatusText } from '../StatusText';
import { Dot } from '../Dot';

describe('Input', () => {
  it('renders with placeholder', () => {
    render(<Input placeholder="Type..." onChange={() => {}} />);
    expect(screen.getByPlaceholderText('Type...')).toBeInTheDocument();
  });

  it('calls onChange', async () => {
    const fn = vi.fn();
    render(<Input onChange={fn} />);
    await userEvent.type(screen.getByRole('textbox'), 'hi');
    expect(fn).toHaveBeenCalled();
  });
});

describe('Select', () => {
  it('renders options', () => {
    render(
      <Select value="a" onChange={() => {}} options={[
        { value: 'a', label: 'Alpha' },
        { value: 'b', label: 'Beta' },
      ]} />
    );
    expect(screen.getAllByRole('option')).toHaveLength(2);
  });
});

describe('Badge', () => {
  it('renders count text', () => {
    render(<Badge>5 tools</Badge>);
    expect(screen.getByText('5 tools')).toBeInTheDocument();
  });
});

describe('Icon', () => {
  it('renders an SVG with correct size', () => {
    const { container } = render(<Icon name="wrench" size={24} />);
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
    expect(svg).toHaveAttribute('width', '24');
  });

  it('renders different icon names', () => {
    const { container } = render(<Icon name="globe" />);
    expect(container.querySelector('svg')).toBeInTheDocument();
  });
});

describe('Checkbox', () => {
  it('renders and responds to click', async () => {
    const fn = vi.fn();
    render(<Checkbox checked={false} onChange={fn} />);
    await userEvent.click(screen.getByRole('checkbox'));
    expect(fn).toHaveBeenCalled();
  });

  it('supports indeterminate state', () => {
    render(<Checkbox checked={false} indeterminate onChange={() => {}} />);
    const cb = screen.getByRole('checkbox') as HTMLInputElement;
    expect(cb.indeterminate).toBe(true);
  });
});

describe('StatusText', () => {
  it('renders text', () => {
    render(<StatusText>Loading...</StatusText>);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });
});

describe('Dot', () => {
  it('renders a span', () => {
    const { container } = render(<Dot />);
    expect(container.querySelector('span')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/components/atoms/__tests__/atoms.test.tsx
```

Expected: FAIL

- [ ] **Step 3: Implement all remaining atoms**

`frontend/src/components/atoms/Input.tsx`:
```tsx
import type { InputHTMLAttributes } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {}

export function Input({ className = '', ...props }: InputProps) {
  return (
    <input
      type="text"
      className={`flex-[3] min-w-0 bg-[var(--input-bg)] text-[var(--text)] border border-[var(--glass-border)] rounded-lg px-4 py-2 text-sm font-light font-mono outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_2px_var(--accent-glow)] transition-all placeholder:text-[var(--text-muted)] ${className}`}
      {...props}
    />
  );
}
```

`frontend/src/components/atoms/Select.tsx`:
```tsx
interface SelectOption {
  value: string;
  label: string;
  group?: string;
}

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  className?: string;
}

export function Select({ value, onChange, options, className = '' }: SelectProps) {
  const groups = new Map<string | undefined, SelectOption[]>();
  for (const opt of options) {
    const key = opt.group;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(opt);
  }

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`bg-[var(--glass-bg)] text-[var(--text)] border border-[var(--glass-border)] rounded-lg px-3 py-1.5 text-sm cursor-pointer outline-none ${className}`}
    >
      {[...groups.entries()].map(([group, opts]) =>
        group ? (
          <optgroup key={group} label={group}>
            {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </optgroup>
        ) : (
          opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)
        )
      )}
    </select>
  );
}
```

`frontend/src/components/atoms/Badge.tsx`:
```tsx
import type { ReactNode } from 'react';

export function Badge({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-[var(--accent-glow)] text-[var(--accent)] border border-[var(--glass-border)] ${className}`}>
      {children}
    </span>
  );
}
```

`frontend/src/components/atoms/Icon.tsx`:
```tsx
const icons = {
  wrench: (
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
  ),
  chevron: <polyline points="9 18 15 12 9 6" />,
  globe: (
    <>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" />
      <path d="M2 12h20" />
    </>
  ),
  close: (
    <>
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </>
  ),
} as const;

export type IconName = keyof typeof icons;

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
}

export function Icon({ name, size = 18, className = '' }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {icons[name]}
    </svg>
  );
}
```

`frontend/src/components/atoms/Checkbox.tsx`:
```tsx
import { useRef, useEffect, type InputHTMLAttributes } from 'react';

interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  indeterminate?: boolean;
}

export function Checkbox({ indeterminate = false, className = '', ...props }: CheckboxProps) {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return (
    <input
      ref={ref}
      type="checkbox"
      className={`accent-[var(--accent)] cursor-pointer ${className}`}
      {...props}
    />
  );
}
```

`frontend/src/components/atoms/StatusText.tsx`:
```tsx
import type { ReactNode } from 'react';

export function StatusText({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <span className={`text-xs text-[var(--text-muted)] font-light ${className}`}>
      {children}
    </span>
  );
}
```

`frontend/src/components/atoms/Dot.tsx`:
```tsx
export function Dot({ delay = '0s', className = '' }: { delay?: string; className?: string }) {
  return (
    <span
      className={`inline-block w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-pulse ${className}`}
      style={{ animationDelay: delay }}
    />
  );
}
```

`frontend/src/components/atoms/index.ts`:
```typescript
export { Button } from './Button';
export { Input } from './Input';
export { Select } from './Select';
export { Badge } from './Badge';
export { Icon } from './Icon';
export { Checkbox } from './Checkbox';
export { StatusText } from './StatusText';
export { Dot } from './Dot';
```

- [ ] **Step 4: Run all atom component tests**

```bash
cd frontend && npx vitest run src/components/atoms/
```

Expected: All tests PASS (~12 tests across 2 test files)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/atoms/
git commit -m "feat: add all UI atom components"
```

---

### CHECKPOINT: Chunk 4 complete

**Verify:** `cd frontend && npx vitest run` — all tests pass (~52 tests).

You now have: typed data atoms, adapters, hooks/providers, and presentational UI atoms. Every layer is tested independently. The next two chunks compose these into visible features.

**Dependency flow:**
```
Chunk 1 (data atoms) ← Chunk 2 (adapters) ← Chunk 3 (hooks/providers)
Chunk 1 (data atoms) ← Chunk 4 (UI atoms — no deps on adapters/hooks)
                         ↓                        ↓
                    Chunk 5 (molecules — combines hooks + UI atoms)
```

---

## Chunk 5: Molecules

**Depends on:** Chunk 3 (hooks) + Chunk 4 (UI atoms). Molecules compose UI atoms and consume hooks.

Each molecule is a self-contained unit that combines a few atoms with minimal logic. After this chunk, every visible piece of the UI exists as a testable component — they just aren't assembled into a page yet.

### Task 20: ModelSelect molecule

**Depends on:** useModels hook (Task 12), Select atom (Task 19)

**Files:**
- Create: `frontend/src/components/molecules/ModelSelect.tsx`
- Create: `frontend/src/components/molecules/__tests__/ModelSelect.test.tsx`

- [ ] **Step 1: Write failing test**

`frontend/src/components/molecules/__tests__/ModelSelect.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ModelSelect } from '../ModelSelect';
import { ModelProvider } from '../../../providers/ModelProvider';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => { mockFetch.mockReset(); });

const modelsResp = {
  models: ['huihui_ai/qwen2.5-coder-abliterate:14b', 'llama3.1:8b'],
  current: 'llama3.1:8b',
};

describe('ModelSelect', () => {
  it('renders model options after loading', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => modelsResp });
    render(<ModelProvider><ModelSelect /></ModelProvider>);
    await waitFor(() => {
      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });
    expect(screen.getAllByRole('option').length).toBeGreaterThanOrEqual(2);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/molecules/__tests__/ModelSelect.test.tsx
```

Expected: FAIL

- [ ] **Step 3: Implement ModelSelect**

`frontend/src/components/molecules/ModelSelect.tsx`:
```tsx
import { Select } from '../atoms/Select';
import { StatusText } from '../atoms/StatusText';
import { useModels } from '../../hooks/useModels';
import { modelId } from '../../atoms/model';

export function ModelSelect() {
  const { models, current, selectModel, loading } = useModels();

  if (loading) return <StatusText>Loading models...</StatusText>;

  const options = models.map((m) => ({
    value: modelId(m),
    label: m.devTeam ? `${m.devTeam}/${m.name}:${m.numParams}` : `${m.name}:${m.numParams}`,
  }));

  return (
    <div className="flex items-center gap-2">
      <Select
        value={current ? modelId(current) : ''}
        onChange={(val) => {
          const model = models.find((m) => modelId(m) === val);
          if (model) selectModel(model);
        }}
        options={[{ value: '', label: 'Select model...' }, ...options]}
      />
      <StatusText>
        {current ? `${current.name}:${current.numParams}` : 'No model selected'}
      </StatusText>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend && npx vitest run src/components/molecules/__tests__/ModelSelect.test.tsx
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/molecules/ModelSelect.tsx frontend/src/components/molecules/__tests__/ModelSelect.test.tsx
git commit -m "feat: add ModelSelect molecule"
```

---

### Task 21: ChatInput, ToolChip, CategoryHeader, ToolRow molecules

**Files:**
- Create: `frontend/src/components/molecules/ChatInput.tsx`
- Create: `frontend/src/components/molecules/ToolChip.tsx`
- Create: `frontend/src/components/molecules/CategoryHeader.tsx`
- Create: `frontend/src/components/molecules/ToolRow.tsx`
- Create: `frontend/src/components/molecules/__tests__/molecules.test.tsx`

- [ ] **Step 1: Write failing tests**

`frontend/src/components/molecules/__tests__/molecules.test.tsx`:
```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatInput } from '../ChatInput';
import { ToolChip } from '../ToolChip';
import { CategoryHeader } from '../CategoryHeader';
import { ToolRow } from '../ToolRow';

describe('ChatInput', () => {
  it('calls onSend when send button clicked', async () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} onCancel={() => {}} onClear={() => {}} streaming={false} />);
    const input = screen.getByPlaceholderText('Type a message...');
    await userEvent.type(input, 'hello');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(onSend).toHaveBeenCalledWith('hello');
  });

  it('shows stop button when streaming', () => {
    render(<ChatInput onSend={() => {}} onCancel={() => {}} onClear={() => {}} streaming={true} />);
    expect(screen.getByRole('button', { name: 'Stop' })).toBeVisible();
  });
});

describe('ToolChip', () => {
  it('shows count', () => {
    render(<ToolChip selected={['a', 'b']} onRemove={() => {}} />);
    expect(screen.getByText('2 tools')).toBeInTheDocument();
  });

  it('hides when no tools selected', () => {
    const { container } = render(<ToolChip selected={[]} onRemove={() => {}} />);
    expect(container.firstChild).toBeNull();
  });
});

describe('CategoryHeader', () => {
  it('renders category name and count', () => {
    render(
      <CategoryHeader
        name="Filesystem"
        count={10}
        selectedCount={5}
        allSelected={false}
        someSelected={true}
        expanded={false}
        onToggleExpand={() => {}}
        onToggleAll={() => {}}
      />
    );
    expect(screen.getByText('Filesystem')).toBeInTheDocument();
    expect(screen.getByText('5/10')).toBeInTheDocument();
  });
});

describe('ToolRow', () => {
  it('renders tool name and description', () => {
    render(<ToolRow name="read_file" description="Read a file" selected={true} onToggle={() => {}} />);
    expect(screen.getByText('read_file')).toBeInTheDocument();
    expect(screen.getByText('Read a file')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/components/molecules/__tests__/molecules.test.tsx
```

Expected: FAIL

- [ ] **Step 3: Implement ChatInput**

`frontend/src/components/molecules/ChatInput.tsx`:
```tsx
import { useState } from 'react';
import { Input } from '../atoms/Input';
import { Button } from '../atoms/Button';

interface ChatInputProps {
  onSend: (text: string) => void;
  onCancel: () => void;
  onClear: () => void;
  streaming: boolean;
}

export function ChatInput({ onSend, onCancel, onClear, streaming }: ChatInputProps) {
  const [text, setText] = useState('');

  const handleSend = () => {
    if (text.trim()) {
      onSend(text.trim());
      setText('');
    }
  };

  return (
    <>
      <Input
        placeholder="Type a message..."
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && !streaming) handleSend(); }}
      />
      <Button variant="ghost" onClick={onClear}>Clear</Button>
      {streaming ? (
        <Button variant="danger" onClick={onCancel}>Stop</Button>
      ) : (
        <Button variant="primary" onClick={handleSend} disabled={!text.trim()}>Send</Button>
      )}
    </>
  );
}
```

- [ ] **Step 4: Implement ToolChip**

`frontend/src/components/molecules/ToolChip.tsx`:
```tsx
import { useState } from 'react';
import { Badge } from '../atoms/Badge';
import { Icon } from '../atoms/Icon';

interface ToolChipProps {
  selected: string[];
  onRemove: (name: string) => void;
}

export function ToolChip({ selected, onRemove }: ToolChipProps) {
  const [showPopup, setShowPopup] = useState(false);

  if (selected.length === 0) return null;

  return (
    <div
      className="relative"
      onMouseEnter={() => setShowPopup(true)}
      onMouseLeave={() => setShowPopup(false)}
    >
      <Badge>
        <Icon name="wrench" size={14} />
        {selected.length} tools
      </Badge>
      {showPopup && (
        <div className="absolute bottom-full left-0 mb-2 bg-[var(--glass-bg-solid)] border border-[var(--glass-border)] rounded-lg p-2 min-w-48 backdrop-blur-xl z-50">
          {selected.map((name) => (
            <div key={name} className="flex items-center justify-between gap-2 py-1 px-2 text-xs text-[var(--text)]">
              <span className="font-mono">{name}</span>
              <span
                className="cursor-pointer text-[var(--danger)] hover:brightness-125"
                onClick={() => onRemove(name)}
              >
                <Icon name="close" size={12} />
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Implement CategoryHeader and ToolRow**

`frontend/src/components/molecules/CategoryHeader.tsx`:
```tsx
import { Checkbox } from '../atoms/Checkbox';
import { Icon } from '../atoms/Icon';

interface CategoryHeaderProps {
  name: string;
  count: number;
  selectedCount: number;
  allSelected: boolean;
  someSelected: boolean;
  expanded: boolean;
  onToggleExpand: () => void;
  onToggleAll: () => void;
}

export function CategoryHeader({
  name, count, selectedCount, allSelected, someSelected,
  expanded, onToggleExpand, onToggleAll,
}: CategoryHeaderProps) {
  return (
    <div
      className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-[var(--glass-highlight)] rounded-lg transition-colors"
      onClick={onToggleExpand}
    >
      <Icon
        name="chevron"
        size={14}
        className={`transition-transform ${expanded ? 'rotate-90' : ''}`}
      />
      <Checkbox
        checked={allSelected}
        indeterminate={someSelected && !allSelected}
        onChange={(e) => { e.stopPropagation(); onToggleAll(); }}
        onClick={(e) => e.stopPropagation()}
      />
      <span className="text-sm text-[var(--text)] font-medium flex-1">{name}</span>
      <span className="text-xs text-[var(--text-muted)] font-mono">{selectedCount}/{count}</span>
    </div>
  );
}
```

`frontend/src/components/molecules/ToolRow.tsx`:
```tsx
import { Checkbox } from '../atoms/Checkbox';

interface ToolRowProps {
  name: string;
  description: string;
  selected: boolean;
  onToggle: () => void;
}

export function ToolRow({ name, description, selected, onToggle }: ToolRowProps) {
  return (
    <div
      className="flex items-center gap-2 px-3 py-1.5 ml-5 hover:bg-[var(--glass-highlight)] rounded-lg cursor-pointer transition-colors"
      onClick={onToggle}
    >
      <Checkbox checked={selected} onChange={onToggle} onClick={(e) => e.stopPropagation()} />
      <span className="text-xs font-mono text-[var(--accent)] min-w-24">{name}</span>
      <span className="text-xs text-[var(--text-muted)] truncate">{description}</span>
    </div>
  );
}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/components/molecules/__tests__/molecules.test.tsx
```

Expected: 6 tests PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/molecules/
git commit -m "feat: add ChatInput, ToolChip, CategoryHeader, ToolRow molecules"
```

---

### Task 22: MessageBubble, ImageThumbnail, ThinkingIndicator molecules

**Files:**
- Create: `frontend/src/components/molecules/MessageBubble.tsx`
- Create: `frontend/src/components/molecules/ImageThumbnail.tsx`
- Create: `frontend/src/components/molecules/ThinkingIndicator.tsx`
- Create: `frontend/src/components/molecules/index.ts`
- Create: `frontend/src/components/molecules/__tests__/message-molecules.test.tsx`

- [ ] **Step 1: Write failing tests**

`frontend/src/components/molecules/__tests__/message-molecules.test.tsx`:
```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MessageBubble } from '../MessageBubble';
import { ImageThumbnail } from '../ImageThumbnail';
import { ThinkingIndicator } from '../ThinkingIndicator';
import type { Message } from '../../../atoms/message';

const userMsg: Message = {
  id: '1', role: 'user', content: 'Hello', images: [], toolCalls: [], timestamp: 1,
};

const assistantMsg: Message = {
  id: '2', role: 'assistant', content: 'Hi there', images: [], toolCalls: [], timestamp: 2,
};

describe('MessageBubble', () => {
  it('renders user message right-aligned', () => {
    const { container } = render(<MessageBubble message={userMsg} />);
    expect(container.firstChild).toHaveClass('self-end');
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('renders assistant message left-aligned', () => {
    const { container } = render(<MessageBubble message={assistantMsg} />);
    expect(container.firstChild).toHaveClass('self-start');
  });
});

describe('ImageThumbnail', () => {
  it('renders image with caption', () => {
    render(<ImageThumbnail src="/img.jpg" filename="img.jpg" sizeKb={42} onClick={() => {}} />);
    expect(screen.getByRole('img')).toHaveAttribute('src', '/img.jpg');
    expect(screen.getByText(/img\.jpg/)).toBeInTheDocument();
  });
});

describe('ThinkingIndicator', () => {
  it('renders with working label', () => {
    render(<ThinkingIndicator label="Working..." elapsed={3} preview="" />);
    expect(screen.getByText('Working...')).toBeInTheDocument();
    expect(screen.getByText('3s')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/components/molecules/__tests__/message-molecules.test.tsx
```

Expected: FAIL

- [ ] **Step 3: Implement MessageBubble**

`frontend/src/components/molecules/MessageBubble.tsx`:
```tsx
import type { Message } from '../../atoms/message';

const roleClasses = {
  user: 'self-end bg-[var(--msg-user)]',
  assistant: 'self-start bg-[var(--msg-assistant)]',
  error: 'self-center bg-transparent text-[var(--danger)] text-center',
};

export function MessageBubble({ message }: { message: Message }) {
  return (
    <div className={`max-w-[75%] px-4 py-3 rounded-xl text-sm leading-relaxed whitespace-pre-wrap break-words font-mono font-light animate-[msgIn_0.25s_ease-out] ${roleClasses[message.role]}`}>
      {message.content}
    </div>
  );
}
```

- [ ] **Step 4: Implement ImageThumbnail**

`frontend/src/components/molecules/ImageThumbnail.tsx`:
```tsx
interface ImageThumbnailProps {
  src: string;
  filename: string;
  sizeKb: number;
  onClick: () => void;
}

export function ImageThumbnail({ src, filename, sizeKb, onClick }: ImageThumbnailProps) {
  return (
    <div className="self-start cursor-pointer" onClick={onClick}>
      <img
        src={src}
        alt={filename}
        className="max-w-[280px] max-h-[200px] rounded-xl border border-[var(--glass-border)] hover:brightness-115 hover:scale-[1.01] transition-all"
      />
      <div className="text-xs text-[var(--text-muted)] font-mono mt-1">
        {filename} ({sizeKb} KB)
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Implement ThinkingIndicator**

`frontend/src/components/molecules/ThinkingIndicator.tsx`:
```tsx
import { Dot } from '../atoms/Dot';

interface ThinkingIndicatorProps {
  label: string;
  elapsed: number;
  preview: string;
}

export function ThinkingIndicator({ label, elapsed, preview }: ThinkingIndicatorProps) {
  return (
    <div className="self-start max-w-[75%] px-4 py-3 rounded-xl bg-[var(--msg-assistant)] border border-[var(--glass-border)]">
      <div className="flex items-center gap-2 mb-1">
        <div className="flex gap-1">
          <Dot delay="0s" />
          <Dot delay="0.2s" />
          <Dot delay="0.4s" />
        </div>
        <span className="text-xs text-[var(--text-secondary)]">{label}</span>
        <span className="text-xs text-[var(--text-muted)] font-mono tabular-nums ml-auto">
          {elapsed}s
        </span>
      </div>
      {preview && (
        <div className="text-xs text-[var(--text-muted)] font-mono truncate max-w-full">
          {preview}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Create barrel export**

`frontend/src/components/molecules/index.ts`:
```typescript
export { ModelSelect } from './ModelSelect';
export { ChatInput } from './ChatInput';
export { ToolChip } from './ToolChip';
export { CategoryHeader } from './CategoryHeader';
export { ToolRow } from './ToolRow';
export { MessageBubble } from './MessageBubble';
export { ImageThumbnail } from './ImageThumbnail';
export { ThinkingIndicator } from './ThinkingIndicator';
```

- [ ] **Step 7: Run all molecule tests**

```bash
cd frontend && npx vitest run src/components/molecules/
```

Expected: All tests PASS (~12 tests across 3 test files)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/molecules/
git commit -m "feat: add MessageBubble, ImageThumbnail, ThinkingIndicator molecules"
```

---

### CHECKPOINT: Chunk 5 complete

**Verify:** `cd frontend && npx vitest run` — all tests pass (~64 tests).

Every visible piece of the UI exists as a standalone, tested component. You can render any molecule in isolation and verify it works. The next chunk assembles them into organisms and the final page.

**Dependency flow:**
```
Chunk 1 (data atoms)
  ← Chunk 2 (adapters)
    ← Chunk 3 (hooks/providers)
      ← Chunk 5 (molecules — use hooks + UI atoms)
Chunk 1 ← Chunk 4 (UI atoms)
            ← Chunk 5 (molecules — compose UI atoms)
               ← Chunk 6 (organisms + page — compose molecules)
```

---

## Chunk 6: Organisms + Pages + Integration

**Depends on:** Chunk 3 (hooks) + Chunk 5 (molecules). This is the assembly phase — molecules become organisms, organisms become the page.

### Task 23: ErrorBoundary utility

**Files:**
- Create: `frontend/src/components/ErrorBoundary.tsx`

- [ ] **Step 1: Implement ErrorBoundary**

`frontend/src/components/ErrorBoundary.tsx`:
```tsx
import { Component, type ReactNode, type ErrorInfo } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="p-4 text-center text-[var(--danger)] text-sm">
          <p>Something went wrong.</p>
          <button
            className="mt-2 px-3 py-1 text-xs border border-[var(--danger)] rounded-lg hover:bg-[var(--danger)] hover:text-white transition-colors"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ErrorBoundary.tsx
git commit -m "feat: add ErrorBoundary component"
```

---

### Task 24: TopBar organism

**Depends on:** ModelSelect molecule, useTheme hook

**Files:**
- Create: `frontend/src/components/organisms/TopBar.tsx`

- [ ] **Step 1: Implement TopBar**

`frontend/src/components/organisms/TopBar.tsx`:
```tsx
import { ModelSelect } from '../molecules/ModelSelect';
import { Select } from '../atoms/Select';
import { Icon } from '../atoms/Icon';
import { useTheme } from '../../hooks/useTheme';

export function TopBar() {
  const { theme, setTheme, themes } = useTheme();

  const themeOptions = themes.map((t) => ({
    value: t.id,
    label: t.label,
    group: t.mode === 'dark' ? 'Dark' : 'Light',
  }));

  return (
    <div className="flex items-center gap-3 px-4 h-12 bg-[var(--glass-bg-solid)] backdrop-blur-xl border-b border-[var(--glass-border)]">
      <div className="flex items-center gap-2 text-[var(--text)] font-medium text-sm">
        <Icon name="globe" size={18} />
        Agentic Chat
      </div>
      <ModelSelect />
      <div className="flex-1" />
      <Select value={theme.id} onChange={setTheme} options={themeOptions} />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/organisms/TopBar.tsx
git commit -m "feat: add TopBar organism"
```

---

### Task 25: Sidebar organism

**Depends on:** CategoryHeader + ToolRow molecules, useTools hook

**Files:**
- Create: `frontend/src/components/organisms/Sidebar.tsx`

- [ ] **Step 1: Implement Sidebar**

`frontend/src/components/organisms/Sidebar.tsx`:
```tsx
import { useState } from 'react';
import { CategoryHeader } from '../molecules/CategoryHeader';
import { ToolRow } from '../molecules/ToolRow';
import { Icon } from '../atoms/Icon';
import { useTools } from '../../hooks/useTools';

interface SidebarProps {
  expanded: boolean;
  onToggle: () => void;
}

export function Sidebar({ expanded, onToggle }: SidebarProps) {
  const { categories, toggleTool, toggleCategory } = useTools();
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());

  const toggleCatExpand = (name: string) => {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  };

  return (
    <div className="flex flex-col bg-[var(--glass-bg-solid)] backdrop-blur-xl border border-[var(--glass-border)] rounded-[14px] m-2 overflow-hidden shadow-[0_4px_24px_rgba(0,0,0,0.15)]">
      <div
        className="flex items-center justify-center p-3 cursor-pointer hover:bg-[var(--glass-highlight)] transition-colors"
        onClick={onToggle}
        title="Toggle tools"
      >
        <Icon name="chevron" size={18} className={`transition-transform ${expanded ? 'rotate-180' : ''}`} />
      </div>

      {expanded && (
        <div className="flex-1 overflow-y-auto px-2 pb-2">
          <div className="text-sm font-semibold text-[var(--text)] px-3 py-2">Tools</div>
          {categories.map((cat) => (
            <div key={cat.name}>
              <CategoryHeader
                name={cat.name}
                count={cat.count}
                selectedCount={cat.selectedCount}
                allSelected={cat.allSelected}
                someSelected={cat.someSelected}
                expanded={expandedCats.has(cat.name)}
                onToggleExpand={() => toggleCatExpand(cat.name)}
                onToggleAll={() => toggleCategory(cat.name)}
              />
              {expandedCats.has(cat.name) && cat.tools.map((tool) => (
                <ToolRow
                  key={tool.name}
                  name={tool.name}
                  description={tool.description}
                  selected={tool.selected}
                  onToggle={() => toggleTool(tool.name)}
                />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/organisms/Sidebar.tsx
git commit -m "feat: add Sidebar organism"
```

---

### Task 26: MessageList organism

**Depends on:** MessageBubble, ImageThumbnail, ThinkingIndicator molecules, useChat hook

**Files:**
- Create: `frontend/src/components/organisms/MessageList.tsx`

- [ ] **Step 1: Implement MessageList**

`frontend/src/components/organisms/MessageList.tsx`:
```tsx
import { useRef, useEffect, useState } from 'react';
import { MessageBubble } from '../molecules/MessageBubble';
import { ImageThumbnail } from '../molecules/ImageThumbnail';
import { ThinkingIndicator } from '../molecules/ThinkingIndicator';
import { useChat } from '../../hooks/useChat';

interface MessageListProps {
  onImageClick: (src: string, caption: string) => void;
}

export function MessageList({ onImageClick }: MessageListProps) {
  const { messages, streaming } = useChat();
  const bottomRef = useRef<HTMLDivElement>(null);
  const [elapsed, setElapsed] = useState(0);

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streaming]);

  // Timer for thinking indicator
  useEffect(() => {
    if (!streaming) { setElapsed(0); return; }
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, [streaming]);

  return (
    <div className="overflow-y-auto px-6 py-5 flex flex-col gap-2">
      {messages.map((msg) => (
        <div key={msg.id}>
          <MessageBubble message={msg} />
          {msg.images.map((img, i) => (
            <ImageThumbnail
              key={i}
              src={img.src}
              filename={img.filename}
              sizeKb={img.sizeKb}
              onClick={() => onImageClick(img.src, img.filename)}
            />
          ))}
        </div>
      ))}
      {streaming && (
        <ThinkingIndicator label="Working..." elapsed={elapsed} preview="" />
      )}
      <div ref={bottomRef} />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/organisms/MessageList.tsx
git commit -m "feat: add MessageList organism"
```

---

### Task 27: InputBar organism

**Depends on:** ChatInput, ToolChip molecules, useChat + useTools hooks

**Files:**
- Create: `frontend/src/components/organisms/InputBar.tsx`

- [ ] **Step 1: Implement InputBar**

`frontend/src/components/organisms/InputBar.tsx`:
```tsx
import { ChatInput } from '../molecules/ChatInput';
import { ToolChip } from '../molecules/ToolChip';
import { useChat } from '../../hooks/useChat';
import { useTools } from '../../hooks/useTools';

export function InputBar() {
  const { sendMessage, cancelStream, clearHistory, streaming } = useChat();
  const { selected, toggleTool } = useTools();

  return (
    <div className="flex items-center gap-2 px-3 py-3 m-2 bg-[var(--glass-bg-solid)] backdrop-blur-xl border-t border-[var(--glass-border)] rounded-xl z-10">
      <ToolChip selected={selected} onRemove={toggleTool} />
      <ChatInput
        onSend={sendMessage}
        onCancel={cancelStream}
        onClear={clearHistory}
        streaming={streaming}
      />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/organisms/InputBar.tsx
git commit -m "feat: add InputBar organism"
```

---

### Task 28: Lightbox organism

**Files:**
- Create: `frontend/src/components/organisms/Lightbox.tsx`

- [ ] **Step 1: Implement Lightbox**

`frontend/src/components/organisms/Lightbox.tsx`:
```tsx
import { useEffect } from 'react';

interface LightboxProps {
  src: string;
  caption: string;
  onClose: () => void;
}

export function Lightbox({ src, caption, onClose }: LightboxProps) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/80 backdrop-blur-sm cursor-pointer"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <img
        src={src}
        alt={caption}
        className="max-w-[90vw] max-h-[85vh] rounded-xl shadow-2xl"
      />
      {caption && (
        <div className="mt-3 text-sm text-white/70 font-mono">{caption}</div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create organisms barrel export**

`frontend/src/components/organisms/index.ts`:
```typescript
export { TopBar } from './TopBar';
export { Sidebar } from './Sidebar';
export { MessageList } from './MessageList';
export { InputBar } from './InputBar';
export { Lightbox } from './Lightbox';
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/organisms/
git commit -m "feat: add Lightbox organism + barrel export"
```

---

### Task 28b: ParticleCanvas component

**Depends on:** Theme atom (Task 6)

Ports the existing inline particle animation (canvas-based, theme-aware color palettes) to a standalone React component.

**Files:**
- Create: `frontend/src/components/atoms/ParticleCanvas.tsx`
- Create: `frontend/src/components/atoms/__tests__/ParticleCanvas.test.tsx`

- [ ] **Step 1: Write failing test**

`frontend/src/components/atoms/__tests__/ParticleCanvas.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { ParticleCanvas } from '../ParticleCanvas';

beforeEach(() => {
  // Mock canvas context
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    closePath: vi.fn(),
    fillStyle: '',
  })) as any;
});

describe('ParticleCanvas', () => {
  it('renders a canvas element', () => {
    const { container } = render(<ParticleCanvas theme="obsidian" />);
    expect(container.querySelector('canvas')).toBeInTheDocument();
  });

  it('applies fixed positioning to fill viewport', () => {
    const { container } = render(<ParticleCanvas theme="obsidian" />);
    const canvas = container.querySelector('canvas')!;
    expect(canvas.className).toContain('fixed');
    expect(canvas.className).toContain('inset-0');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/atoms/__tests__/ParticleCanvas.test.tsx
```

Expected: FAIL

- [ ] **Step 3: Implement ParticleCanvas**

`frontend/src/components/atoms/ParticleCanvas.tsx`:
```tsx
import { useRef, useEffect } from 'react';

const PALETTES: Record<string, string[]> = {
  obsidian:  ['#2a4a8a','#4060b0','#6080d0','#3050a0','#1a3070'],
  carbon:    ['#20a060','#30c080','#50e0a0','#18804a','#40d890'],
  amethyst:  ['#7030b0','#9050d0','#b070f0','#6020a0','#a060e0'],
  frost:     ['#3050c0','#4060e0','#5080ff','#2040a0','#6090ff'],
  sand:      ['#b08020','#c89830','#dab050','#a07018','#d0a040'],
  blossom:   ['#c02060','#d84080','#f060a0','#a01848','#e85098'],
};

const COUNT = 80;
const FIELD = 3;

interface Particle {
  x: number; y: number; r: number;
  dx: number; dy: number; opacity: number;
  rgb: [number, number, number];
}

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

interface ParticleCanvasProps {
  theme: string;
}

export function ParticleCanvas({ theme }: ParticleCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let W = 0, H = 0;
    const particles: Particle[] = [];
    let animId: number;

    function resize() {
      W = canvas!.width = window.innerWidth;
      H = canvas!.height = window.innerHeight;
    }

    function spawn(i: number, scatter: boolean) {
      const pal = PALETTES[theme] ?? PALETTES.obsidian;
      const color = pal[Math.floor(Math.random() * pal.length)];
      const rgb = hexToRgb(color);
      const r = Math.random() * 1.2 + 0.3;
      particles[i] = {
        x: Math.random() * W,
        y: scatter ? Math.random() * H * FIELD : -(Math.random() * H * 0.5),
        r, dx: (Math.random() - 0.5) * 0.06,
        dy: Math.random() * 0.12 + 0.04,
        opacity: Math.random() * 0.3 + 0.08, rgb,
      };
    }

    function draw() {
      ctx!.clearRect(0, 0, W, H);
      for (let i = 0; i < COUNT; i++) {
        const p = particles[i];
        p.x += p.dx; p.y += p.dy;
        if (p.y > H * FIELD) spawn(i, false);
        const screenY = ((p.y % (H * FIELD)) + H * FIELD) % (H * FIELD) - H;
        if (screenY > -10 && screenY < H + 10) {
          ctx!.beginPath();
          ctx!.arc(p.x, screenY, p.r, 0, Math.PI * 2);
          ctx!.fillStyle = `rgba(${p.rgb[0]},${p.rgb[1]},${p.rgb[2]},${p.opacity})`;
          ctx!.fill();
        }
      }
      animId = requestAnimationFrame(draw);
    }

    resize();
    for (let i = 0; i < COUNT; i++) spawn(i, true);
    draw();
    window.addEventListener('resize', resize);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, [theme]);

  return <canvas ref={canvasRef} className="fixed inset-0 pointer-events-none z-0" />;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/components/atoms/__tests__/ParticleCanvas.test.tsx
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/atoms/ParticleCanvas.tsx frontend/src/components/atoms/__tests__/ParticleCanvas.test.tsx
git commit -m "feat: add ParticleCanvas component with theme-aware color palettes"
```

---

### Task 29: ChatPage — full assembly

**Depends on:** All organisms (Tasks 23-28, 28b), ErrorBoundary (Task 23)

This is where the pile of abstractions becomes a cohesive unit. Every atom, molecule, and organism snaps into the grid.

**Files:**
- Create: `frontend/src/pages/ChatPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Implement ChatPage**

`frontend/src/pages/ChatPage.tsx`:
```tsx
import { useState, useCallback } from 'react';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { TopBar } from '../components/organisms/TopBar';
import { Sidebar } from '../components/organisms/Sidebar';
import { MessageList } from '../components/organisms/MessageList';
import { InputBar } from '../components/organisms/InputBar';
import { Lightbox } from '../components/organisms/Lightbox';
import { ParticleCanvas } from '../components/atoms/ParticleCanvas';
import { useTheme } from '../hooks/useTheme';

export function ChatPage() {
  const { theme } = useTheme();
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
  const [lightbox, setLightbox] = useState<{ src: string; caption: string } | null>(null);

  const handleImageClick = useCallback((src: string, caption: string) => {
    setLightbox({ src, caption });
  }, []);

  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
      <ParticleCanvas theme={theme.id} />
      <ErrorBoundary>
        <TopBar />
      </ErrorBoundary>

      <div
        className="flex-1 grid grid-rows-[1fr_auto] transition-[grid-template-columns] duration-300 ease-in-out overflow-hidden"
        style={{
          gridTemplateColumns: sidebarExpanded ? '35rem 1fr' : '4.5rem 1fr',
        }}
      >
        <ErrorBoundary>
          <Sidebar
            expanded={sidebarExpanded}
            onToggle={() => setSidebarExpanded((p) => !p)}
          />
        </ErrorBoundary>

        <ErrorBoundary>
          <MessageList onImageClick={handleImageClick} />
        </ErrorBoundary>

        {/* InputBar spans both columns */}
        <ErrorBoundary>
          <div className="col-span-2">
            <InputBar />
          </div>
        </ErrorBoundary>
      </div>

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

- [ ] **Step 2: Update App.tsx to use ChatPage**

`frontend/src/App.tsx`:
```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from './providers/ThemeProvider';
import { ModelProvider } from './providers/ModelProvider';
import { ToolProvider } from './providers/ToolProvider';
import { ChatProvider } from './providers/ChatProvider';
import { WebSocketProvider } from './providers/WebSocketProvider';
import { ChatPage } from './pages/ChatPage';

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <ModelProvider>
          <ToolProvider>
            <ChatProvider>
              <WebSocketProvider enabled={false}>
                <Routes>
                  <Route path="/" element={<ChatPage />} />
                </Routes>
              </WebSocketProvider>
            </ChatProvider>
          </ToolProvider>
        </ModelProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
```

- [ ] **Step 3: Add msgIn keyframe to index.css**

Append to `frontend/src/index.css`:
```css
@keyframes msgIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
```

- [ ] **Step 4: Write ChatPage assembly test**

`frontend/src/pages/__tests__/ChatPage.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ChatPage } from '../ChatPage';
import { ThemeProvider } from '../../providers/ThemeProvider';
import { ModelProvider } from '../../providers/ModelProvider';
import { ToolProvider } from '../../providers/ToolProvider';
import { ChatProvider } from '../../providers/ChatProvider';
import { WebSocketProvider } from '../../providers/WebSocketProvider';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

// Mock canvas for ParticleCanvas
HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
  clearRect: vi.fn(), beginPath: vi.fn(), arc: vi.fn(),
  fill: vi.fn(), closePath: vi.fn(), fillStyle: '',
})) as any;

function renderWithProviders() {
  mockFetch.mockResolvedValue({ ok: true, json: async () => ({ models: [], current: null, tools: {} }) });
  return render(
    <MemoryRouter>
      <ThemeProvider>
        <ModelProvider>
          <ToolProvider>
            <ChatProvider>
              <WebSocketProvider enabled={false}>
                <ChatPage />
              </WebSocketProvider>
            </ChatProvider>
          </ToolProvider>
        </ModelProvider>
      </ThemeProvider>
    </MemoryRouter>
  );
}

describe('ChatPage', () => {
  it('renders without crashing with all providers', () => {
    const { container } = renderWithProviders();
    expect(container.firstChild).toBeInTheDocument();
  });

  it('error boundary isolates failures — page still renders if one organism throws', () => {
    // If a child of ErrorBoundary throws, other ErrorBoundary siblings should survive
    const { container } = renderWithProviders();
    // The grid container should exist even if individual organisms error
    expect(container.querySelector('.grid')).toBeInTheDocument();
  });
});
```

- [ ] **Step 5: Verify full app renders**

```bash
cd frontend && npm run dev
```

Expected: Full chat UI renders — topbar with model select + theme picker, collapsible sidebar with animated grid transition, message area, input bar with tool chip, particle canvas background. Theme switching works. (Chat functionality requires Flask backend running.)

- [ ] **Step 6: Run full test suite**

```bash
cd frontend && npx vitest run
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ frontend/src/App.tsx frontend/src/index.css
git commit -m "feat: assemble ChatPage with grid layout, particles, and animated sidebar"
```

---

### CHECKPOINT: Chunk 6 complete

**Verify:** `cd frontend && npx vitest run` — all tests pass. `npm run dev` renders the full UI.

**Integration test:** Start Flask (`python main.py --serve`) and Vite (`cd frontend && npm run dev`). Visit http://localhost:5173. Select a model, toggle tools, send a message, verify streaming works, test theme switching, test sidebar expand/collapse animation.

At this point the React frontend is feature-complete. The final chunk cleans up the Flask backend.

**Dependency flow (complete):**
```
Chunk 1 (data atoms)
  ← Chunk 2 (adapters)
    ← Chunk 3 (hooks/providers)
      ← Chunk 5 (molecules)
        ← Chunk 6 (organisms + page) ← Chunk 7 (backend cleanup)
  ← Chunk 4 (UI atoms)
    ← Chunk 5 (molecules)
```

---

## Chunk 7: Flask Backend Cleanup + Production Build

**Depends on:** Chunk 6 complete and integration-tested. Only then is it safe to remove the old frontend.

### Task 30: Production build configuration

**Files:**
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: Configure build output**

Update `frontend/vite.config.ts` to set build output directory:
```typescript
build: {
  outDir: 'dist',
  emptyDirOnBuild: true,
},
```

- [ ] **Step 2: Build and verify output**

```bash
cd frontend && npm run build
ls frontend/dist/
```

Expected: `index.html`, `assets/` directory with JS/CSS bundles.

- [ ] **Step 3: Commit**

```bash
git add frontend/vite.config.ts
git commit -m "feat: configure Vite production build"
```

---

### Task 31: Flask catch-all route for SPA

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Update auth middleware to allow SPA routes and assets**

The `_is_public_path()` function in `main.py` currently blocks non-API paths that aren't `/`, `/main.css`, `/health`, or `/static/*`. After the refactor, Vite bundles live under `/assets/` and React Router creates client-side routes. Update the auth middleware so non-`/api/` paths pass through:

```python
# Replace the existing _PUBLIC_PATHS and _is_public_path with:
_PUBLIC_PATHS = frozenset({"/", "/health"})

def _is_public_path(path: str) -> bool:
    if path in _PUBLIC_PATHS or path.startswith("/static/"):
        return True
    # Allow frontend assets and SPA routes (anything not under /api/)
    if not path.startswith("/api/"):
        return True
    return False
```

- [ ] **Step 2: Add static file serving + SPA catch-all**

Add to `main.py` after the existing route definitions:

```python
import os as _os

_FRONTEND_DIST = _os.path.join(_os.path.dirname(__file__), "frontend", "dist")

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    """Serve React SPA from frontend/dist/."""
    full = _os.path.join(_FRONTEND_DIST, path)
    if path and _os.path.isfile(full):
        return send_file(full)
    index = _os.path.join(_FRONTEND_DIST, "index.html")
    if _os.path.isfile(index):
        return send_file(index)
    return "Frontend not built. Run: cd frontend && npm run build", 404
```

- [ ] **Step 2: Verify Flask serves the React build**

```bash
cd frontend && npm run build
cd .. && python main.py --serve
# Visit http://localhost:5000 — should serve React app
```

Expected: React app loads from Flask, all API calls work (same origin, no proxy needed).

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add Flask SPA catch-all for production React serving"
```

---

### Task 32: Remove old inline frontend

**Files:**
- Modify: `main.py` (delete INDEX_HTML, old routes)
- Delete: `main.css`

- [ ] **Step 1: Delete INDEX_HTML template string from main.py**

Remove the entire `INDEX_HTML = r"""..."""` string and the routes that served it:
- The `INDEX_HTML` variable (~lines 213-835)
- The `GET /` route that called `render_template_string(INDEX_HTML)`
- The `GET /main.css` route

- [ ] **Step 2: Delete main.css**

```bash
rm main.css
```

- [ ] **Step 3: Verify the app still works**

```bash
cd frontend && npm run build && cd ..
python main.py --serve
# Visit http://localhost:5000
```

Expected: React app loads, all features work. No references to the old template.

- [ ] **Step 4: Run backend tests if any exist**

```bash
cd /home/ermer/devproj/python/agentic_w_langchain_ollama && python -m pytest tests/ -v 2>/dev/null || echo "No backend tests found"
```

- [ ] **Step 5: Commit**

```bash
git add main.py && git rm main.css
git commit -m "refactor: remove inline HTML/JS/CSS frontend from Flask"
```

---

### Task 33: Add frontend to .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add node_modules and dist to .gitignore**

Append to `.gitignore`:
```
# Frontend
frontend/node_modules/
frontend/dist/
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: add frontend build artifacts to .gitignore"
```

---

### CHECKPOINT: Chunk 7 complete — refactor done

**Final verification checklist:**

- [ ] `cd frontend && npx vitest run` — all tests pass
- [ ] `cd frontend && npm run build` — production build succeeds
- [ ] `python main.py --serve` — Flask serves React SPA + API
- [ ] Theme switching works (all 6 themes)
- [ ] Model selection works
- [ ] Tool browsing with sidebar expand/collapse animation works
- [ ] Chat with streaming works
- [ ] Image thumbnails + lightbox work
- [ ] Tool chip shows selected tools with remove
- [ ] Clear history works
- [ ] Cancel stream works
- [ ] Page refresh preserves route (React Router catch-all)
- [ ] No references to `INDEX_HTML`, `main.css`, or `render_template_string` remain in `main.py`

**Final dependency flow:**
```
Chunk 1: Scaffold + Data Atoms ──────────────────────────── foundation
    ↓
Chunk 2: API Adapters ──────────────────────────────────── Flask ↔ atoms bridge
    ↓
Chunk 3: Hooks + Providers ─────────────────────────────── React state layer
    ↓                          ↑
Chunk 4: UI Atom Components ──── (parallel to Chunk 3) ── visual primitives
    ↓                          ↓
Chunk 5: Molecules ─────────────────────────────────────── composed UI + logic
    ↓
Chunk 6: Organisms + Pages ─────────────────────────────── full assembly
    ↓
Chunk 7: Backend Cleanup ──────────────────────────────── remove old, ship new
```
