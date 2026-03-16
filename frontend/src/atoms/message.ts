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

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  images: ImageAttachment[];
  toolCalls: ToolCallInfo[];
  timestamp: number;
}

let _counter = 0;
function genId(): string {
  return `msg-${Date.now()}-${++_counter}`;
}

export function createMessage(role: MessageRole, content: string): Message {
  return {
    id: genId(), role, content, images: [], toolCalls: [], timestamp: Date.now(),
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
    images: [], toolCalls: [], timestamp: 0,
  };
}
