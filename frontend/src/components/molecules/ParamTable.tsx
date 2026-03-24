import type { ToolParam } from '../../api/workflowGroups';

interface ParamTableProps {
  params: Record<string, ToolParam>;
  interactive: boolean;
  values: Record<string, unknown>;
  onChange: (name: string, value: unknown) => void;
}

export function ParamTable({ params, interactive, values, onChange }: ParamTableProps) {
  const entries = Object.entries(params);

  if (entries.length === 0) {
    return <span className="text-[10px] text-[var(--text-muted)] italic">No parameters</span>;
  }

  return (
    <table className="w-full text-[10px] font-mono border-collapse">
      <thead>
        <tr className="text-[var(--text-muted)]">
          <th className="text-left py-1 pr-2">Name</th>
          <th className="text-left py-1 pr-2">Type</th>
          <th className="text-left py-1 pr-2">Req</th>
          {interactive ? (
            <th className="text-left py-1">Value</th>
          ) : (
            <th className="text-left py-1">Description</th>
          )}
        </tr>
      </thead>
      <tbody>
        {entries.map(([name, param]) => (
          <tr key={name} className="border-t border-[var(--glass-border)]">
            <td className="py-1 pr-2 text-[var(--accent)]">{name}</td>
            <td className="py-1 pr-2 text-[var(--text-muted)]">{param.type}</td>
            <td className="py-1 pr-2">{param.required ? '\u2713' : ''}</td>
            {interactive ? (
              <td className="py-1">
                {param.type === 'boolean' ? (
                  <label className="flex items-center gap-1 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={!!values[name]}
                      onChange={(e) => onChange(name, e.target.checked)}
                    />
                  </label>
                ) : param.type === 'integer' || param.type === 'number' ? (
                  <input
                    type="number"
                    value={values[name] as number ?? ''}
                    onChange={(e) => onChange(name, e.target.value ? Number(e.target.value) : '')}
                    className="w-full bg-transparent border-b border-[var(--glass-border)] text-[var(--text)] outline-none focus:border-[var(--accent)]"
                  />
                ) : (
                  <input
                    type="text"
                    value={values[name] as string ?? ''}
                    onChange={(e) => onChange(name, e.target.value)}
                    className="w-full bg-transparent border-b border-[var(--glass-border)] text-[var(--text)] outline-none focus:border-[var(--accent)]"
                    placeholder={param.description}
                  />
                )}
              </td>
            ) : (
              <td className="py-1 text-[var(--text-muted)]">{param.description}</td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
