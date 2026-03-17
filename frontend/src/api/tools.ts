import type { Tool, ToolCategory } from '../atoms/tool';
import { buildCategory } from '../atoms/tool';
import type { ApiResponse } from '../atoms/api';

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
  [/^(read_file|file_info|write_file|append_file|replace_in_file|insert_at_line|delete_lines|copy_file|move_file|delete_file)$/, 'File Operations'],
  [/^(list_dir|tree|make_dir|find_files|find_definition|grep)$/, 'Navigation & Search'],
  [/^(web_search|fetch_url)$/, 'Web'],
  [/^ebay_/, 'eBay'],
  [/^(amazon_search)$/, 'Amazon'],
  [/^craigslist_/, 'Craigslist'],
  [/^(cross_platform_search|deal_finder|enrichment_pipeline)$/, 'Marketplace'],
];

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

  // Stable ordering: File Ops, Nav & Search, Web, eBay, then any extras
  const order = ['File Operations', 'Navigation & Search', 'Web', 'eBay', 'Amazon', 'Craigslist', 'Marketplace', 'Other'];
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
    const resp = await fetch('/api/tools');
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
    const checkResp = await fetch('/api/tools');
    if (!checkResp.ok) return { data: [], error: `Failed: ${checkResp.status}` };
    const checkJson: ToolsResponse = await checkResp.json();
    const isSelected = checkJson.selected.some((t) => t.name === name);

    const endpoint = isSelected ? '/api/tools/deselect' : '/api/tools/select';
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index }),
    });
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
    const checkResp = await fetch('/api/tools');
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
      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ index: t.index }),
      });
      if (resp.ok) lastJson = await resp.json();
    }
    return transform(lastJson);
  } catch (e) {
    return { data: [], error: String(e) };
  }
}
