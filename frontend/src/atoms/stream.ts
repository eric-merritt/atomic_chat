export type StreamEvent =
  | { type: 'token'; token: string }
  | { type: 'tool_call'; tool: string; input: string }
  | { type: 'tool_result'; tool: string; output: string }
  | { type: 'image'; src: string; filename: string; sizeKb: number }
  | { type: 'error'; message: string };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function parseStreamLine(raw: any): StreamEvent | null {
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
  if ('error' in raw) {
    return { type: 'error', message: raw.error };
  }
  return null;
}
