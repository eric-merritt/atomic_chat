export type MessageRole = 'user' | 'assistant' | 'error';

export interface ImageAttachment {
  src: string;
  filename: string;
  sizeKb: number;
}

export interface ToolCallInfo {
  id?: string;
  tool: string;
  input: string;
  params?: Record<string, unknown>;
}

export interface ToolCallPair {
  tool: string
  params: unknown        // parsed from tool_call input JSON string
  result: unknown | null // null until tool_result arrives
  status: 'streaming' | 'done'
  contentOffset: number  // char position in message.content when this tool was called
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  images: ImageAttachment[];
  toolCalls: ToolCallInfo[];  // kept for backward compat
  toolPairs: ToolCallPair[];  // new: paired call+result for rendering
  timestamp: number;
}

let _counter = 0;
function genId(): string {
  return `msg-${Date.now()}-${++_counter}`;
}

export function createMessage(role: MessageRole, content: string): Message {
  return {
    id: genId(), role, content, images: [],
    toolCalls: [], toolPairs: [], timestamp: Date.now(),
  };
}

export function createMessageFromHistory(entry: {
  role: string;
  content: string;
}): Message {
  return {
    id: genId(),
    role: entry.role as MessageRole,
    content: entry.content,
    images: [], toolCalls: [], toolPairs: [], timestamp: 0,
  };
}
