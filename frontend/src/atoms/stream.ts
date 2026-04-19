export type StreamEvent =
  | { type: 'token'; token: string }
  | { type: 'tool_call'; tool: string; input: string }
  | { type: 'tool_result'; tool: string; output: string }
  | { type: 'image'; src: string; filename: string; sizeKb: number }
  | { type: 'error'; message: string }
  | { type: 'meta'; conversationId: string | null }
  | { type: 'recommendation'; groups: string[]; reason: string }
  | { type: 'context_pct'; pct: number };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function parseStreamLine(raw: any): StreamEvent | null {
  if ('conversation_id' in raw) {
    return { type: 'meta', conversationId: raw.conversation_id ?? null };
  }
  if ('type' in raw && raw.type === 'meta') {
    return { type: 'meta', conversationId: raw.conversation_id ?? null };
  }
  if ('chunk' in raw) {
    return { type: 'token', token: raw.chunk };
  }
  if ('token' in raw) {
    return { type: 'token', token: raw.token };
  }
  if ('tool_call' in raw) {
    return { type: 'tool_call', tool: raw.tool_call.tool, input: raw.tool_call.input };
  }
  if ('tool_result' in raw) {
    return { type: 'tool_result', tool: raw.tool_result.tool, output: raw.tool_result.output };
  }
  if ('image' in raw) {
    return {
      type: 'image',
      src: raw.image.src,
      filename: raw.image.filename,
      sizeKb: raw.image.size_kb,
    };
  }
  if ('recommendation' in raw) {
    return {
      type: 'recommendation',
      groups: raw.recommendation.groups,
      reason: raw.recommendation.reason,
    };
  }
  if ('error' in raw) {
    return { type: 'error', message: raw.error };
  }
  if ('context_pct' in raw) {
    return { type: 'context_pct', pct: raw.context_pct };
  }
  return null;
}
