import { useChat } from '../../hooks/useChat';

export function NewConversationButton() {
  const { messages, newConversation } = useChat();

  if (messages.length === 0) return null;

  return (
    <button
      onClick={newConversation}
      className="px-3 py-1 text-xs rounded-lg border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-white transition-colors cursor-pointer"
    >
      + New Conversation
    </button>
  );
}
