import { useState, useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useChat } from '../hooks/useChat';
import { useWorkspace } from '../hooks/useWorkspace';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { TopBar } from '../components/organisms/TopBar';
import { Sidebar } from '../components/organisms/Sidebar';
import { MessageList } from '../components/organisms/MessageList';
import { InputBar } from '../components/organisms/InputBar';
import { TaskList } from '../components/organisms/TaskList';
import { ToolWorkspace } from '../components/organisms/ToolWorkspace';
import { ChatPopover } from '../components/molecules/ChatPopover';
import { Lightbox } from '../components/organisms/Lightbox';
import { ParticleCanvas } from '../components/atoms/ParticleCanvas';
import { useTheme } from '../hooks/useTheme';

export function ChatPage() {
  const { theme } = useTheme();
  const { layout } = useWorkspace();
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
  const [lightbox, setLightbox] = useState<{ src: string; caption: string } | null>(null);
  const [chatPopoverOpen, setChatPopoverOpen] = useState(false);
  const [searchParams] = useSearchParams();
  const { loadConversation } = useChat();

  useEffect(() => {
    const convId = searchParams.get('conversation');
    if (convId) loadConversation(convId);
  }, [searchParams, loadConversation]);

  const handleImageClick = useCallback((src: string, caption: string) => {
    setLightbox({ src, caption });
  }, []);

  const sidebarWidth = sidebarExpanded ? '22rem' : '6rem';

  const gridColumns = (() => {
    switch (layout) {
      case 'workspace-chat':
        return `${sidebarWidth} 1fr 22rem`;
      case 'workspace-inputbar':
        return `${sidebarWidth} 1fr`;
      default:
        return `${sidebarWidth} 1fr`;
    }
  })();

  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
      <ParticleCanvas theme={theme.id} />
      <ErrorBoundary>
        <TopBar />
      </ErrorBoundary>

      <div
        className="flex-1 grid grid-rows-[1fr_auto] transition-[grid-template-columns] duration-300 ease-in-out overflow-hidden"
        style={{ gridTemplateColumns: gridColumns }}
      >
        {/* Sidebar — always present */}
        <ErrorBoundary>
          <Sidebar
            expanded={sidebarExpanded}
            onToggle={() => setSidebarExpanded((p) => !p)}
          />
        </ErrorBoundary>

        {/* Center: Chat (default) or Workspace */}
        {layout === 'default' ? (
          <ErrorBoundary>
            <MessageList onImageClick={handleImageClick} />
          </ErrorBoundary>
        ) : (
          <ErrorBoundary>
            <ToolWorkspace />
          </ErrorBoundary>
        )}

        {/* Right column: slim chat (workspace-chat layout only) */}
        {layout === 'workspace-chat' && (
          <ErrorBoundary>
            <div className="overflow-hidden border-l border-[var(--glass-border)]">
              <MessageList onImageClick={handleImageClick} />
            </div>
          </ErrorBoundary>
        )}

        {/* Bottom row: spans all columns */}
        <div style={{ gridColumn: '1 / -1' }} className="flex items-stretch shrink-0">
          <ErrorBoundary>
            <div className="flex items-stretch p-2 transition-[width] duration-300 ease-in-out" style={{ width: sidebarWidth }}>
              <TaskList sidebarExpanded={sidebarExpanded} style={{}} />
            </div>
          </ErrorBoundary>
          <ErrorBoundary>
            <div className="flex-1 flex items-stretch">
              <InputBar />
              {layout === 'workspace-inputbar' && (
                <button
                  className="flex items-center justify-center w-10 shrink-0 cursor-pointer text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors text-lg"
                  onClick={() => setChatPopoverOpen((p) => !p)}
                  title="Open chat"
                >
                  Chat
                </button>
              )}
            </div>
          </ErrorBoundary>
        </div>
      </div>

      {/* Chat popover */}
      <ChatPopover open={chatPopoverOpen} onClose={() => setChatPopoverOpen(false)} />

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
