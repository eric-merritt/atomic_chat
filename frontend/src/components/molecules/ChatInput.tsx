import { useState } from 'react';
import { Input } from '../atoms/Input';
import { Button } from '../atoms/Button';

interface ChatInputProps {
  onSend: (text: string) => void;
  onCancel: () => void;
  onClear: () => void;
  streaming: boolean;
}

export function ChatInput({ onSend, onCancel, onClear, streaming }: ChatInputProps) {
  const [text, setText] = useState('');

  const handleSend = () => {
    if (text.trim()) {
      onSend(text.trim());
      setText('');
    }
  };

  return (
    <>
      <Input
        placeholder="Type a message..."
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && !streaming) handleSend(); }}
      />
      <Button variant="ghost" onClick={onClear}>Clear</Button>
      {streaming ? (
        <Button variant="danger" onClick={onCancel}>Stop</Button>
      ) : (
        <Button variant="primary" onClick={handleSend} disabled={!text.trim()}>Send</Button>
      )}
    </>
  );
}
