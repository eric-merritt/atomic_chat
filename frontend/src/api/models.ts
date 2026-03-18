import type { Model } from '../atoms/model';
import { parseModelString, modelId } from '../atoms/model';
import type { ApiResponse } from '../atoms/api';

export async function fetchModels(): Promise<ApiResponse<Model[]> & { current: string | null }> {
  try {
    const resp = await fetch('/api/models', { credentials: 'include' });
    if (!resp.ok) {
      return { data: [], error: `Failed to fetch models: ${resp.status}`, current: null };
    }
    const json = await resp.json();
    const models = (json.models as string[]).map(parseModelString);
    return { data: models, current: json.current ?? null };
  } catch (e) {
    return { data: [], error: String(e), current: null };
  }
}

export async function selectModel(model: Model): Promise<ApiResponse<string>> {
  const id = modelId(model);
  try {
    const resp = await fetch('/api/models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: id }),
      credentials: 'include',
    });
    if (!resp.ok) {
      return { data: '', error: `Failed to select model: ${resp.status}` };
    }
    const json = await resp.json();
    return { data: json.model };
  } catch (e) {
    return { data: '', error: String(e) };
  }
}
