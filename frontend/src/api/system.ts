import type { ApiResponse } from '../atoms/api';

export async function fetchSystemPrompt(): Promise<ApiResponse<string>> {
  try {
    const resp = await fetch('/api/system');
    if (!resp.ok) return { data: '', error: `Failed: ${resp.status}` };
    const json = await resp.json();
    return { data: json.system_prompt };
  } catch (e) {
    return { data: '', error: String(e) };
  }
}

export async function setSystemPrompt(prompt: string): Promise<ApiResponse<string>> {
  try {
    const resp = await fetch('/api/system', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ system_prompt: prompt }),
    });
    if (!resp.ok) return { data: '', error: `Failed: ${resp.status}` };
    const json = await resp.json();
    return { data: json.system_prompt };
  } catch (e) {
    return { data: '', error: String(e) };
  }
}
