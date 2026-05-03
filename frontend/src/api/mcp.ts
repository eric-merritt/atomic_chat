export interface McpServer {
  id: string;
  name: string;
  vendor: string;
  url: string;
  category: string;
  tier: 'free' | 'freemium' | 'paid';
  self_hostable: boolean;
  partnership_potential: boolean;
  description: string;
}

export interface McpCatalogResponse {
  schema_version: number;
  as_of: string;
  categories: string[];
  count: number;
  servers: McpServer[];
}

export interface McpFilters {
  tier?: 'free' | 'freemium' | 'paid';
  category?: string;
  self_hostable?: boolean;
}

export async function fetchMcpServers(filters: McpFilters = {}): Promise<McpCatalogResponse> {
  const params = new URLSearchParams();
  if (filters.tier) params.set('tier', filters.tier);
  if (filters.category) params.set('category', filters.category);
  if (filters.self_hostable !== undefined) params.set('self_hostable', String(filters.self_hostable));

  const query = params.toString();
  const res = await fetch(`/api/mcp/servers${ query ? `?${ query }` : '' }`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch MCP servers');
  return res.json();
}
