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
