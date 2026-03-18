export interface Conversation {
  id: string;
  title: string;
  folder: string | null;
  model: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: string;
  role: 'user' | 'assistant' | 'error';
  content: string;
  images: { src: string; filename: string; sizeKb: number }[];
  tool_calls: { tool: string; input: string }[];
  created_at: string;
}

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
  page: number;
  limit: number;
}
