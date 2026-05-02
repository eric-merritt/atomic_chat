type Section = 'conversations' | 'profile' | 'keys' | 'connections' | 'accounting' | 'restricted';

interface DashboardNavProps {
  active: Section;
  onSelect: (section: Section) => void;
}

const NAV_ITEMS: { id: Section; label: string }[] = [
  { id: 'profile', label: 'Profile' },
  { id: 'conversations', label: 'Conversations' },
  { id: 'accounting', label: 'Journal Entry' },
  { id: 'keys', label: 'API Keys' },
  { id: 'connections', label: 'Connections' },
  { id: 'restricted', label: 'Restricted Tools' },
];

export function DashboardNav({ active, onSelect }: DashboardNavProps) {
  return (
    <nav className="flex flex-col gap-1 p-3">
      <a href="/" className="text-sm text-[var(--accent)] hover:underline mb-4 px-3">
        &larr; Back to Chat
      </a>
      {NAV_ITEMS.map((item) => (
        <button
          key={item.id}
          onClick={() => onSelect(item.id)}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors cursor-pointer ${
            active === item.id
              ? 'bg-[var(--msg-user)] text-[var(--accent)] font-medium'
              : 'text-[var(--text)] hover:bg-[var(--msg-user)]'
          }`}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
}
