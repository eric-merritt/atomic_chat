import { createContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { Model } from '../atoms/model';
import { modelId } from '../atoms/model';
import { fetchModels as apiFetchModels, selectModel as apiSelectModel } from '../api/models';

interface ModelContextValue {
  models: Model[];
  current: Model | null;
  selectModel: (model: Model) => Promise<void>;
  loading: boolean;
}

export const ModelContext = createContext<ModelContextValue | null>(null);

export function ModelProvider({ children }: { children: ReactNode }) {
  const [models, setModels] = useState<Model[]>([]);
  const [current, setCurrent] = useState<Model | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetchModels().then((result) => {
      setModels(result.data);
      if (result.current) {
        const match = result.data.find(
          (m) => modelId(m) === result.current
        );
        setCurrent(match ?? null);
      }
      setLoading(false);
    }).catch(() => {
      setLoading(false);
    });
  }, []);

  const selectModel = useCallback(async (model: Model) => {
    await apiSelectModel(model);
    setCurrent(model);
  }, []);

  return (
    <ModelContext.Provider value={{ models, current, selectModel, loading }}>
      {children}
    </ModelContext.Provider>
  );
}
