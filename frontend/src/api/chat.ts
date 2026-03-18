export async function streamChatAsync(message: string, conversationId?: string | null): Promise<{
  reader: ReadableStreamDefaultReader<Uint8Array>;
  abort: () => void;
}> {
  const controller = new AbortController();
  const resp = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_id: conversationId }),
    signal: controller.signal,
    credentials: 'include',
  });
  if (!resp.ok || !resp.body) throw new Error(`Stream failed: ${resp.status}`);
  return {
    reader: resp.body.getReader(),
    abort: () => controller.abort(),
  };
}

export async function cancelChat(): Promise<void> {
  await fetch('/api/chat/cancel', { method: 'POST', credentials: 'include' });
}
