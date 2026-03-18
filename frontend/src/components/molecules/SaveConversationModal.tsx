import { useState } from 'react';
import { Modal } from '../atoms/Modal';
import { createConversation } from '../../api/conversations';
import { useChat } from '../../hooks/useChat';

interface SaveConversationModalProps {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  onDiscard: () => void;
}

export function SaveConversationModal({ open, onClose, onSaved, onDiscard }: SaveConversationModalProps) {
  const { messages } = useChat();
  const defaultTitle = messages[0]?.content?.slice(0, 50) || 'New Conversation';
  const [title, setTitle] = useState(defaultTitle);

  const inputClass = "w-full bg-[var(--input-bg)] text-[var(--text)] border border-[var(--glass-border)] rounded-lg px-4 py-2 text-sm font-mono outline-none focus:border-[var(--accent)]";
  const btnClass = "px-4 py-2 text-sm rounded-lg cursor-pointer";

  const handleSave = async () => {
    await createConversation(title || defaultTitle);
    onSaved();
  };

  return (
    <Modal open={open} onClose={onClose}>
      <h3 className="text-lg font-semibold text-[var(--text)] mb-4">Save Conversation</h3>
      <div className="space-y-3">
        <input
          type="text"
          value={title}
          onChange={e => setTitle(e.target.value)}
          placeholder="Conversation title"
          className={inputClass}
        />
        <div className="flex gap-2">
          <button onClick={handleSave} className={`${btnClass} bg-[var(--accent)] text-white hover:opacity-90`}>
            Save
          </button>
          <button onClick={onDiscard} className={`${btnClass} border border-[var(--glass-border)] text-[var(--text)] hover:bg-[var(--msg-user)]`}>
            Discard
          </button>
        </div>
      </div>
    </Modal>
  );
}
