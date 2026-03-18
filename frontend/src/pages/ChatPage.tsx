import { useState, useCallback } from 'react';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { TopBar } from '../components/organisms/TopBar';
import { Sidebar } from '../components/organisms/Sidebar';
import { MessageList } from '../components/organisms/MessageList';
import { InputBar } from '../components/organisms/InputBar';
import { Lightbox } from '../components/organisms/Lightbox';
import { ParticleCanvas } from '../components/atoms/ParticleCanvas';
import { useTheme } from '../hooks/useTheme';

export function ChatPage() {
  const { theme } = useTheme();
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
  const [lightbox, setLightbox] = useState<{ src: string; caption: string } | null>(null);

  const handleImageClick = useCallback((src: string, caption: string) => {
    setLightbox({ src, caption });
  }, []);

  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
      <ParticleCanvas theme={theme.id} />
      <ErrorBoundary>
        <TopBar />
      </ErrorBoundary>

      <div
        className="flex-1 grid grid-rows-[1fr_auto] transition-[grid-template-columns] duration-300 ease-in-out overflow-hidden"
        style={{
          gridTemplateColumns: sidebarExpanded ? '22rem 1fr' : '6rem 1fr',
        }}
      >
        <ErrorBoundary>
          <Sidebar
            expanded={sidebarExpanded}
            onToggle={() => setSidebarExpanded((p) => !p)}
          />
        </ErrorBoundary>

        <ErrorBoundary>
          <MessageList onImageClick={handleImageClick} />
        </ErrorBoundary>

        {/* InputBar spans both columns */}
        <ErrorBoundary>
          <div className="col-span-2">
            <InputBar />
          </div>
        </ErrorBoundary>
      </div>

      {lightbox && (
        <Lightbox
          src={lightbox.src}
          caption={lightbox.caption}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  );
}
