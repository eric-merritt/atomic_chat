import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { ConversationItem } from '../molecules/ConversationItem';
import { listConversations, deleteConversation } from '../../api/conversations';
import type { Conversation } from '../../atoms/conversation';

export function ConversationList() {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const load = useCallback(async () => {
    const data = await listConversations({ q: search || undefined, page, limit: 20 });
    setConversations(data.conversations);
    setTotal(data.total);
  }, [search, page]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async (id: string) => {
    await deleteConversation(id);
    load();
  };

  return (
    <div>
      <h2 className="text-lg font-semibold text-[var(--text)] mb-4">Conversations</h2>
      <input
        type="text"
        placeholder="Search conversations..."
        value={search}
        onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        className="w-full bg-[var(--input-bg)] text-[var(--text)] border border-[var(--glass-border)] rounded-lg px-4 py-2 text-sm font-mono outline-none focus:border-[var(--accent)] transition-all mb-4"
      />
      {conversations.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">No conversations yet.</p>
      ) : (
        <div className="border border-[var(--glass-border)] rounded-lg overflow-hidden">
          {conversations.map((c) => (
            <ConversationItem
              key={c.id}
              title={c.title}
              date={c.updated_at}
              folder={c.folder}
              onClick={() => navigate(`/?conversation=${c.id}`)}
              onDelete={() => handleDelete(c.id)}
            />
          ))}
        </div>
      )}
      {total > 20 && (
        <div className="flex justify-center gap-2 mt-4">
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}
            className="text-sm text-[var(--accent)] disabled:opacity-50 cursor-pointer">&larr; Prev</button>
          <span className="text-sm text-[var(--text-muted)]">Page {page}</span>
          <button disabled={page * 20 >= total} onClick={() => setPage(p => p + 1)}
            className="text-sm text-[var(--accent)] disabled:opacity-50 cursor-pointer">Next &rarr;</button>
        </div>
      )}
    </div>
  );
}
