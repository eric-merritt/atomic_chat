import { createContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { Model } from '../atoms/model';
import { modelId } from '../atoms/model';
import { fetchModels as apiFetchModels, selectModel as apiSelectModel } from '../api/models';

interface ModelContextValue {
  models: Model[];
  current: Model | null;
  saveDir: string;
  selectModel: (model: Model) => Promise<void>;
  loading: boolean;
  error: string | null;
}

export const ModelContext = createContext<ModelContextValue | null>(null);

export function ModelProvider({ children }: { children: ReactNode }) {
  const [models, setModels] = useState<Model[]>([]);
  const [current, setCurrent] = useState<Model | null>(null);
  const [saveDir, setSaveDir] = useState<string>('~/Downloads');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetchModels().then((result) => {
      setModels(result.data);
      setSaveDir(result.saveDir);
      if (result.current) {
        // Find the full object that matches the current ID string
        const match = result.data.find((m) => modelId(m) === result.current);
        setCurrent(match ?? null);
      }
      setLoading(false);
    }).catch((e: unknown) => {
      const msg = e instanceof Error ? e.message : String(e);
      console.error('[ModelProvider] Failed to load models from /api/models:', msg);
      setError('Failed to load available models — backend may be offline. Reload the page or check that the server is running.');
      setLoading(false);
    });
  }, []);

  const selectModel = useCallback(async (model: Model) => {
    await apiSelectModel(model);
    setCurrent(model);
  }, []);

  return (
    <ModelContext.Provider value={{ models, current, saveDir, selectModel, loading, error }}>
      {children}
    </ModelContext.Provider>
  );
}
