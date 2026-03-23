import { useState, useCallback } from 'react';
import { ChatInput } from '../molecules/ChatInput';
import { useChat } from '../../hooks/useChat';

export function InputBar() {
  const { sendMessage, cancelStream, clearHistory, streaming, ready, toolActivities } = useChat();
  const [pendingMsg, setPendingMsg] = useState<string | null>(null);

  const handleSend = useCallback((text: string) => {
    if (streaming && toolActivities.length > 0) {
      setPendingMsg(text);
    } else {
      sendMessage(text);
    }
  }, [streaming, toolActivities, sendMessage]);

  const handleMoveOn = useCallback(() => {
    if (pendingMsg) {
      cancelStream();
      sendMessage(pendingMsg);
      setPendingMsg(null);
    }
  }, [pendingMsg, cancelStream, sendMessage]);

  const handleDismiss = useCallback(() => {
    setPendingMsg(null);
  }, []);

  return (
    <div className="relative flex items-center gap-2 px-3 py-3 m-2 bg-[var(--glass-bg-solid)] backdrop-blur-xl border border-[var(--accent)] rounded-xl z-10">
      <ChatInput
        onSend={handleSend}
        onCancel={cancelStream}
        onClear={clearHistory}
        streaming={streaming}
        disabled={!ready}
      />

      {pendingMsg !== null && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-4 py-3 rounded-xl
          bg-[var(--glass-bg-solid)] border border-[var(--accent)] shadow-lg
          flex items-center gap-3 text-xs font-mono whitespace-nowrap z-20
          animate-[msgIn_0.15s_ease-out]">
          <span className="inline-block w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse" />
          <span className="text-[var(--text-secondary)]">Tools are still running</span>
          <button
            onClick={handleMoveOn}
            className="px-3 py-1 rounded-lg bg-[var(--accent)] text-[var(--bg-base)] font-semibold
              hover:opacity-90 transition-opacity cursor-pointer"
          >
            Move On
          </button>
          <button
            onClick={handleDismiss}
            className="px-3 py-1 rounded-lg border border-[var(--text-muted)] text-[var(--text-muted)]
              hover:text-[var(--text)] hover:border-[var(--text)] transition-colors cursor-pointer"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}
