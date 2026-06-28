import { useWorkspace } from "../../hooks/useWorkspace";

export function GraphExplorer() {
  const {
    graphExcludedTypes,
    graphToggleExcludedType,
    graphVizDepth,
    graphSetVizDepth,
    graphSearchInput,
    graphSetSearchInput,
    graphSearchLoading,
    graphHighlightCount,
    graphTaskQuery,
    graphSetTaskQuery,
    graphToolLoading,
    graphMatchedTools,
    graphLoading,
    graphData,
    graphReload,
    NODE_COLORS,
  } = useWorkspace();

  const inputClass =
    "w-full px-2 py-1 text-sm rounded bg-[var(--input-bg)] border border-[var(--glass-border)] text-[var(--text)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)]";

  const NODE_TYPES = [
    "Root",
    "Directory",
    "DependencyList",
    "Class",
    "Function",
    "File",
    "State",
    "Prop",
    "Rule",
  ];

  return (
    <div className="flex-1 overflow-y-auto px-3 pb-3 flex flex-col text-md">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-xs text-[var(--text-muted)]">
          {graphLoading
            ? "Loading..."
            : `${graphData?.nodes.length || 0} nodes · ${graphData?.edges.length || 0} edges`}
        </span>
        <button
          onClick={graphReload}
          className="ml-auto px-2 py-0.5 text-xs rounded border border-[var(--glass-border)] text-[var(--text-muted)] hover:text-[var(--text)] hover:border-[var(--accent)] transition-colors"
        >
          Reload
        </button>
      </div>

      <div className="flex flex-col gap-2 mb-4">
        <div className="text-md text-[var(--text-muted)]">
          <span className="font-bold">Types</span> - Click to Toggle
        </div>
        <div className="flex flex-wrap gap-1.5">
          {NODE_TYPES.map((t) => {
            const excluded = graphExcludedTypes.has(t);
            return (
              <button
                key={t}
                onClick={() => graphToggleExcludedType(t)}
                className={`p-2 text-sm rounded border transition-colors cursor-pointer ${
                  excluded
                    ? "border-[var(--glass-border)] text-[var(--text-muted)] opacity-40 line-through"
                    : "border-[var(--accent)] text-[var(--text)]"
                }`}
                title={excluded ? `Click to show ${t}` : `Click to hide ${t}`}
              >
                <span
                  className="inline-block w-2 h-2 rounded-full mr-1"
                  style={{
                    backgroundColor: excluded
                      ? "transparent"
                      : NODE_COLORS[t]?.bg,
                    border: `1px solid ${excluded ? "var(--text-muted)" : NODE_COLORS[t]?.border}`,
                  }}
                />
                {t}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-col gap-2 mb-4">
        <div className="text-md text-[var(--text-muted)]">
          <span className="font-bold">Depth</span>
        </div>
        <div className="flex items-center gap-2 text-md text-[var(--text-muted)] w-full">
          <input
            type="range"
            min={1}
            max={3}
            value={graphVizDepth}
            onChange={(e) => graphSetVizDepth(Number(e.target.value))}
            className="flex-1 accent-[var(--accent)]"
          />
          <span>{graphVizDepth}</span>
        </div>
      </div>

      <div className="flex flex-col gap-2 mb-4">
        <div className="text-md text-[var(--text-muted)]">
          <span className="font-bold">Preview Context Filtering</span>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={graphSearchInput}
            onChange={(e) => graphSetSearchInput(e.target.value)}
            placeholder="Name, summary, file..."
            className={`${inputClass} flex-1`}
          />
          {graphSearchLoading && (
            <svg className="animate-spin h-4 w-4 text-[var(--accent)]" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
        </div>
        {graphHighlightCount > 0 && (
          <div className="text-md text-[var(--text-muted)]">
            {graphHighlightCount} matches
          </div>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <div className="text-md text-[var(--text-muted)]">
          <span className="font-bold">Preview Tool Retrieval</span>
        </div>
        <div className="flex items-start gap-2">
          <textarea
            value={graphTaskQuery}
            onChange={(e) => graphSetTaskQuery(e.target.value)}
            placeholder="Describe a task"
            rows={2}
            className={`${inputClass} resize-none flex-1`}
          />
          {graphToolLoading && (
            <svg className="animate-spin h-4 w-4 text-[var(--accent)] mt-2" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
        </div>
        {graphMatchedTools.length > 0 && (
          <div className="space-y-1.5 max-h-40 overflow-y-auto">
            {graphMatchedTools.map((t) => (
              <div
                key={t.name}
                className="p-1.5 rounded bg-[var(--glass-bg-solid)] border border-[var(--glass-border)]"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-[var(--text)]">
                    {t.name}
                  </span>
                  <span className="text-sm text-[var(--accent)]">
                    {t.score}
                  </span>
                </div>
                <span className="text-sm text-[var(--text-muted)]">
                  {t.category}
                </span>
                <p className="text-sm text-[var(--text-secondary)] mt-0.5 line-clamp-2">
                  {t.call_summary || t.summary}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

    </div>
  );
}
