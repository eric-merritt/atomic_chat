import { useState, useEffect, useCallback } from 'react';
import { fetchMcpServers } from '../api/mcp';
import type { McpServer, McpFilters } from '../api/mcp';

interface McpServersState {
  servers: McpServer[];
  categories: string[];
  asOf: string;
  loading: boolean;
  error: string | null;
}

export function useMcpServers(filters: McpFilters = {}) {
  const [state, setState] = useState<McpServersState>({
    servers: [],
    categories: [],
    asOf: '',
    loading: true,
    error: null,
  });

  const filterKey = JSON.stringify(filters);

  const load = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));
    try {
      const data = await fetchMcpServers(filters);
      setState({ servers: data.servers, categories: data.categories, asOf: data.as_of, loading: false, error: null });
    } catch (err) {
      setState(prev => ({ ...prev, loading: false, error: err instanceof Error ? err.message : 'Unknown error' }));
    }
  }, [filterKey]);

  useEffect(() => { load(); }, [load]);

  return { ...state, reload: load };
}
