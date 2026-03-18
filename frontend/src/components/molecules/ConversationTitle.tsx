import { useState } from 'react';
import { updateConversation } from '../../api/conversations';
import { useChat } from '../../hooks/useChat';

export function ConversationTitle() {
  const { conversationId, messages } = useChat();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState('');

  if (!conversationId || messages.length === 0) return null;

  const displayTitle = title || messages[0]?.content?.slice(0, 50) || 'Conversation';

  const handleSave = async () => {
    if (conversationId && title.trim()) {
      await updateConversation(conversationId, { title: title.trim() });
    }
    setEditing(false);
  };

  if (editing) {
    return (
      <input
        autoFocus
        value={title}
        onChange={e => setTitle(e.target.value)}
        onBlur={handleSave}
        onKeyDown={e => { if (e.key === 'Enter') handleSave(); }}
        className="text-sm text-[var(--text)] bg-transparent border-b border-[var(--accent)] outline-none font-medium"
      />
    );
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-[var(--text)] font-medium truncate">{displayTitle}</span>
      <button
        onClick={() => { setTitle(displayTitle); setEditing(true); }}
        className="text-xs text-[var(--text-muted)] hover:text-[var(--accent)] cursor-pointer"
      >
        ✎
      </button>
    </div>
  );
}
