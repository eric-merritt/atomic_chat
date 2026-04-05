const OPTS: RequestInit = { credentials: 'include' };
const HEADERS = { 'Content-Type': 'application/json' };

export async function listConversations(params?: { q?: string; folder?: string; page?: number; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.q) sp.set('q', params.q);
  if (params?.folder) sp.set('folder', params.folder);
  if (params?.page) sp.set('page', String(params.page));
  if (params?.limit) sp.set('limit', String(params.limit));
  const resp = await fetch(`/api/conversations?${sp}`, OPTS);
  return resp.json();
}

export async function getConversation(id: string, page = 1, limit = 20) {
  const resp = await fetch(`/api/conversations/${id}?page=${page}&limit=${limit}`, OPTS);
  return resp.json();
}

export async function createConversation(title: string, model?: string, folder?: string) {
  const resp = await fetch('/api/conversations', {
    ...OPTS, method: 'POST', headers: HEADERS,
    body: JSON.stringify({ title, model, folder }),
  });
  return resp.json();
}

export async function updateConversation(id: string, data: { title?: string; folder?: string }) {
  const resp = await fetch(`/api/conversations/${id}`, {
    ...OPTS, method: 'PATCH', headers: HEADERS,
    body: JSON.stringify(data),
  });
  return resp.json();
}

export async function deleteConversation(id: string) {
  await fetch(`/api/conversations/${id}`, { ...OPTS, method: 'DELETE' });
}

// ── Conversation Tasks ──────────────────────────────────────────────────────

export interface ConversationTaskDTO {
  id: string;
  title: string;
  status: string;
  depends_on: string | null;
  created_at: string | null;
}

export async function getConversationTasks(conversationId: string) {
  const resp = await fetch(`/api/conversations/${conversationId}/tasks`, OPTS);
  return resp.json() as Promise<{ tasks: ConversationTaskDTO[] }>;
}

export async function createConversationTask(conversationId: string, title: string, dependsOn?: string) {
  const resp = await fetch(`/api/conversations/${conversationId}/tasks`, {
    ...OPTS, method: 'POST', headers: HEADERS,
    body: JSON.stringify({ title, depends_on: dependsOn }),
  });
  return resp.json();
}

export async function updateConversationTask(conversationId: string, taskId: string, data: { title?: string; status?: string; depends_on?: string | null }) {
  const resp = await fetch(`/api/conversations/${conversationId}/tasks/${taskId}`, {
    ...OPTS, method: 'PATCH', headers: HEADERS,
    body: JSON.stringify(data),
  });
  return resp.json();
}

export async function deleteConversationTask(conversationId: string, taskId: string) {
  await fetch(`/api/conversations/${conversationId}/tasks/${taskId}`, { ...OPTS, method: 'DELETE' });
}
