import { ChatInput } from '../molecules/ChatInput';
import { useChat } from '../../hooks/useChat';

export function InputBar() {
  const { sendMessage, cancelStream, clearHistory, streaming, ready, recommendation, acceptRecommendation, dismissRecommendation } = useChat();

  return (
    <div className="flex flex-1 flex-shrink w-full items-center gap-2 px-3 py-3 m-2 bg-[var(--glass-bg-solid)] backdrop-blur-xl border border-[var(--accent)] rounded-xl z-10">
      <ChatInput
        onSend={sendMessage}
        onCancel={cancelStream}
        onClear={clearHistory}
        streaming={streaming}
        disabled={!ready}
      />

      {recommendation && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-4 py-3 rounded-xl
          bg-[var(--glass-bg-solid)] border border-[var(--accent)] backdrop-blur-xl
          flex items-center gap-3 shadow-lg z-20
          animate-[msgIn_0.15s_ease-out]">
          <span className="inline-block w-2 h-2 rounded-full bg-[var(--accent)]" />
          <span className="text-[var(--text-primary)] text-sm">
            <strong>+ {recommendation.groups.join(', ')}</strong>
            <span className="text-[var(--text-muted)] ml-2">&mdash; {recommendation.reason}</span>
          </span>
          <button
            onClick={acceptRecommendation}
            className="px-3 py-1 rounded-lg bg-[var(--accent)] text-[var(--bg-base)] font-semibold
              text-sm hover:opacity-90 transition-opacity cursor-pointer"
          >
            Accept
          </button>
          <button
            onClick={dismissRecommendation}
            className="px-3 py-1 rounded-lg border border-[var(--text-muted)] text-[var(--text-muted)]
              text-sm hover:opacity-80 transition-opacity cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

    </div>
  );
}
