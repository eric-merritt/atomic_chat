import { useState } from 'react';
import { DashboardNav } from '../components/organisms/DashboardNav';
import { ConversationList } from '../components/organisms/ConversationList';
import { ProfilePanel } from '../components/organisms/ProfilePanel';
import { ApiKeyPanel } from '../components/organisms/ApiKeyPanel';
import { ConnectionsPanel } from '../components/organisms/ConnectionsPanel';
import { JournalEntryForm } from '../components/organisms/JournalEntryForm';
import { ParticleCanvas } from '../components/atoms/ParticleCanvas';
import { useTheme } from '../hooks/useTheme';

type Section = 'conversations' | 'profile' | 'keys' | 'connections' | 'accounting';

export function DashboardPage() {
  const { theme } = useTheme();
  const [section, setSection] = useState<Section>('profile');

  const panels: Record<Section, React.ReactNode> = {
    profile: <ProfilePanel />,
    conversations: <ConversationList />,
    accounting: <JournalEntryForm />,
    keys: <ApiKeyPanel />,
    connections: <ConnectionsPanel />,
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
