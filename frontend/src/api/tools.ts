import type { Tool, ToolCategory } from '../atoms/tool';
import { buildCategory } from '../atoms/tool';
import type { ApiResponse } from '../atoms/api';

const CREDS: RequestInit = { credentials: 'include' };
const POST_CREDS = (body: object): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
  credentials: 'include',
});

/* ── API shape ────────────────────────────────────────────────── */

interface RawTool {
  index: number;
  name: string;
  description: string;
  params: Record<string, any>;
}

interface ToolsResponse {
  available: RawTool[];
  selected: RawTool[];
}

/* ── Category inference from tool name ────────────────────────── */

const CATEGORY_RULES: [RegExp, string][] = [
  [/^(read|info|ls|tree|write|append|replace|insert|delete|copy|move|mkdir|grep|find|definition)$/, 'Filesystem'],
  [/^(web_search|fetch_url)$/, 'Web'],
  [/^ebay_/, 'Marketplace'],
  [/^(amazon_search)$/, 'Marketplace'],
  [/^craigslist_/, 'Marketplace'],
  [/^(cross_platform_search|deal_finder|enrichment_pipeline)$/, 'Marketplace'],
];

export function getSubcategory(name: string): string | undefined {
  if (/^ebay_/.test(name)) return 'eBay';
  if (/^(amazon_search)$/.test(name)) return 'Amazon';
  if (/^craigslist_/.test(name)) return 'Craigslist';
  if (/^(cross_platform_search|deal_finder|enrichment_pipeline)$/.test(name)) return 'Cross-Platform';
  return undefined;
}

function inferCategory(name: string): string {
  for (const [re, cat] of CATEGORY_RULES) {
    if (re.test(name)) return cat;
  }
  return 'Other';
}

/* ── Transform flat list → grouped categories ─────────────────── */

function groupIntoCategories(allTools: (RawTool & { selected: boolean })[]): ToolCategory[] {
  const groups = new Map<string, Tool[]>();

  for (const t of allTools) {
    const cat = inferCategory(t.name);
    const tool: Tool = {
      name: t.name,
      description: t.description,
      params: t.params,
      category: cat,
      selected: t.selected,
    };
    if (!groups.has(cat)) groups.set(cat, []);
    groups.get(cat)!.push(tool);
  }

  // Stable ordering
  const order = ['Filesystem', 'Web', 'Marketplace', 'Other'];
  const sorted = [...groups.entries()].sort((a, b) => {
    const ai = order.indexOf(a[0]), bi = order.indexOf(b[0]);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });

  return sorted.map(([name, tools]) => buildCategory(name, tools));
}

/* ── Index lookup (needed for select/deselect API) ────────────── */

let _indexByName = new Map<string, number>();

function buildIndex(resp: ToolsResponse) {
  _indexByName = new Map();
  for (const t of [...resp.available, ...resp.selected]) {
    _indexByName.set(t.name, t.index);
  }
}

/* ── API calls ────────────────────────────────────────────────── */

function transform(resp: ToolsResponse): ApiResponse<ToolCategory[]> {
  buildIndex(resp);
  const selected = new Set(resp.selected.map((t) => t.name));
  const all = [...resp.available, ...resp.selected].map((t) => ({
    ...t,
    selected: selected.has(t.name),
  }));
  // Sort by original index to keep stable ordering within categories
  all.sort((a, b) => a.index - b.index);
  return { data: groupIntoCategories(all) };
}

export async function fetchTools(): Promise<ApiResponse<ToolCategory[]>> {
  try {
    const resp = await fetch('/api/tools', CREDS);
    if (!resp.ok) return { data: [], error: `Failed: ${resp.status}` };
    const json: ToolsResponse = await resp.json();
    return transform(json);
  } catch (e) {
    return { data: [], error: String(e) };
  }
}

export async function toggleTool(name: string): Promise<ApiResponse<ToolCategory[]>> {
  try {
    const index = _indexByName.get(name);
    if (index === undefined) return { data: [], error: `Unknown tool: ${name}` };

    // Check current state from categories to decide select vs deselect
    const checkResp = await fetch('/api/tools', CREDS);
    if (!checkResp.ok) return { data: [], error: `Failed: ${checkResp.status}` };
    const checkJson: ToolsResponse = await checkResp.json();
    const isSelected = checkJson.selected.some((t) => t.name === name);

    const endpoint = isSelected ? '/api/tools/deselect' : '/api/tools/select';
    const resp = await fetch(endpoint, POST_CREDS({ index }));
    if (!resp.ok) return { data: [], error: `Failed: ${resp.status}` };
    const json: ToolsResponse = await resp.json();
    return transform(json);
  } catch (e) {
    return { data: [], error: String(e) };
  }
}

export async function toggleCategory(name: string): Promise<ApiResponse<ToolCategory[]>> {
  try {
    // Fetch current state
    const checkResp = await fetch('/api/tools', CREDS);
    if (!checkResp.ok) return { data: [], error: `Failed: ${checkResp.status}` };
    const checkJson: ToolsResponse = await checkResp.json();
    const selectedNames = new Set(checkJson.selected.map((t) => t.name));

    // Determine which tools are in this category
    const allTools = [...checkJson.available, ...checkJson.selected];
    const catTools = allTools.filter((t) => inferCategory(t.name) === name);

    // If all are selected, deselect all; otherwise select all
    const allSelected = catTools.every((t) => selectedNames.has(t.name));
    const endpoint = allSelected ? '/api/tools/deselect' : '/api/tools/select';

    let lastJson: ToolsResponse = checkJson;
    for (const t of catTools) {
      const shouldAct = allSelected ? selectedNames.has(t.name) : !selectedNames.has(t.name);
      if (!shouldAct) continue;
      const resp = await fetch(endpoint, POST_CREDS({ index: t.index }));
      if (resp.ok) lastJson = await resp.json();
    }
    return transform(lastJson);
  } catch (e) {
    return { data: [], error: String(e) };
  }
}
