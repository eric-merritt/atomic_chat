export interface HierarchyNode {
  label: string
  depth: number        // indent = depth * 2 non-breaking spaces
  isFile: boolean      // underline + onFileClick handler
  href?: string        // file path (isFile) or URL (isExternal)
  isExternal?: boolean // open in new tab
}

interface Props {
  nodes: HierarchyNode[]
  onFileClick: (path: string) => void
}

export function HierarchyRenderer({ nodes, onFileClick }: Props) {
  return (
    <div className="font-mono text-xs leading-relaxed">
      {nodes.map((node, i) => {
        const pad = '\u00A0'.repeat(node.depth * 2)

        if (node.isExternal && node.href) {
          return (
            <div key={i} className="text-[var(--text-muted)]">
              {pad}
              <a
                href={node.href}
                target="_blank"
                rel="noopener noreferrer"
                className="underline text-[var(--accent)] hover:brightness-125 transition-[filter]"
              >
                {node.label}
              </a>
            </div>
          )
        }

        if (node.isFile && node.href) {
          return (
            <div key={i} className="text-[var(--text-muted)]">
              {pad}
              <span
                className="underline text-[var(--accent)] hover:brightness-125 transition-[filter] cursor-pointer"
                onClick={() => onFileClick(node.href!)}
              >
                {node.label}
              </span>
            </div>
          )
        }

        return (
          <div key={i} className="text-[var(--text-muted)]">
            {pad}{node.label}
          </div>
        )
      })}
    </div>
  )
}
