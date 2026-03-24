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
