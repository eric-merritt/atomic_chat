import type { Message } from '../../atoms/message';

const roleClasses = {
  user: 'self-end bg-[var(--msg-user)]',
  assistant: 'self-start bg-[var(--msg-assistant)]',
  error: 'self-center bg-transparent text-[var(--danger)] text-center',
};

export function MessageBubble({ message }: { message: Message }) {
  return (
    <div className={`max-w-[75%] px-4 py-3 rounded-xl text-sm leading-relaxed whitespace-pre-wrap break-words font-mono font-light text-[var(--accent)] animate-[msgIn_0.25s_ease-out] ${roleClasses[message.role]}`}>
      {message.content}
    </div>
  );
}
