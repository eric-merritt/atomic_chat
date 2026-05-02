import { useChat } from '../../hooks/useChat';
import { Button } from '../atoms/Button';

export function BashConfirmBar() {
  const { pendingBashConfirm, approveBashCommand, declineBashCommand } = useChat();
  if (!pendingBashConfirm) return null;

  return (
    <div className="flex items-center gap-3 px-4 py-2.5 bg-[var(--glass-bg-solid)] border-t-2 border-[var(--accent)] text-sm animate-in slide-in-from-bottom-2 duration-200">
      <div className="flex-1 min-w-0 flex items-baseline gap-2 flex-wrap">
        <span className="text-[var(--text-muted)] shrink-0">{pendingBashConfirm.description}</span>
        <code className="font-mono text-xs text-[var(--accent)] bg-[var(--glass-bg)] border border-[var(--glass-border)] px-2 py-0.5 rounded truncate max-w-sm">
          {pendingBashConfirm.command}
        </code>
      </div>
      <div className="flex gap-2 shrink-0">
        <Button variant="ghost" onClick={declineBashCommand}>Decline</Button>
        <Button variant="primary" onClick={approveBashCommand}>Run</Button>
      </div>
    </div>
  );
}
