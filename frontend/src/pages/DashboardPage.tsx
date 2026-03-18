import { useState } from 'react';
import { DashboardNav } from '../components/organisms/DashboardNav';
import { ParticleCanvas } from '../components/atoms/ParticleCanvas';
import { useTheme } from '../hooks/useTheme';

type Section = 'conversations' | 'profile' | 'keys' | 'connections';

function PlaceholderPanel({ title }: { title: string }) {
  return (
    <div>
      <h2 className="text-lg font-semibold text-[var(--text)] mb-4">{title}</h2>
      <p className="text-sm text-[var(--text-muted)]">Coming soon...</p>
    </div>
  );
}

export function DashboardPage() {
  const { theme } = useTheme();
  const [section, setSection] = useState<Section>('conversations');

  const panels: Record<Section, React.ReactNode> = {
    conversations: <PlaceholderPanel title="Conversations" />,
    profile: <PlaceholderPanel title="Profile" />,
    keys: <PlaceholderPanel title="API Keys" />,
    connections: <PlaceholderPanel title="Connections" />,
  };

  return (
    <div className="h-screen flex bg-[var(--bg-base)]">
      <ParticleCanvas theme={theme.id} />
      <div className="w-64 border-r border-[var(--accent)] backdrop-blur-md">
        <DashboardNav active={section} onSelect={setSection} />
      </div>
      <div className="flex-1 overflow-y-auto p-6">
        {panels[section]}
      </div>
    </div>
  );
}
