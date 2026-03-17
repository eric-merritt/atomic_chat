import { ChatInput } from '../molecules/ChatInput';
import { ToolChip } from '../molecules/ToolChip';
import { useChat } from '../../hooks/useChat';
import { useTools } from '../../hooks/useTools';

export function InputBar() {
  const { sendMessage, cancelStream, clearHistory, streaming, ready } = useChat();
  const { selected, toggleTool } = useTools();

  return (
    <div className="flex items-center gap-2 px-3 py-3 m-2 bg-[var(--glass-bg-solid)] backdrop-blur-xl border border-[var(--accent)] rounded-xl z-10">
      <div className="w-[15%] min-w-[120px] shrink-0 flex justify-center">
        <ToolChip selected={selected} onRemove={toggleTool} />
      </div>
      <ChatInput
        onSend={sendMessage}
        onCancel={cancelStream}
        onClear={clearHistory}
        streaming={streaming}
        disabled={!ready}
      />
    </div>
  );
}
