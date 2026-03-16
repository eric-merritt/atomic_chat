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
