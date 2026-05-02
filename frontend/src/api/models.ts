import { parseModelString, modelId } from '../atoms/model';
import type { Model } from '../atoms/model';

interface ModelsResponse {
  models: string[];
  current: string | null;
}

export async function fetchModels(): Promise<{ data: Model[]; current: string | null }> {
  const res = await fetch('/api/models', { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch models');

  const json: ModelsResponse = await res.json();
  return {
    data: (json.models ?? []).map(parseModelString),
    current: json.current,
  };
}

export async function selectModel(model: Model): Promise<void> {
  const id = modelId(model);

  const res = await fetch('/api/models', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: id }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Failed to switch model: ${err}`);
  }
}