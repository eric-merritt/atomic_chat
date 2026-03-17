import { ChatInput } from '../molecules/ChatInput';
import { ToolChip } from '../molecules/ToolChip';
import { useChat } from '../../hooks/useChat';
import { useTools } from '../../hooks/useTools';

export function InputBar() {
  const { sendMessage, cancelStream, clearHistory, streaming } = useChat();
  const { selected, toggleTool } = useTools();

  return (
    <div className="flex items-center gap-2 px-3 py-3 m-2 bg-[var(--glass-bg-solid)] backdrop-blur-xl border border-[var(--accent)] rounded-xl z-10">
      <ToolChip selected={selected} onRemove={toggleTool} />
      <ChatInput
        onSend={sendMessage}
        onCancel={cancelStream}
        onClear={clearHistory}
        streaming={streaming}
      />
    </div>
  );
}
