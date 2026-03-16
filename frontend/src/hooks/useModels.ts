import { useContext } from 'react';
import { ModelContext } from '../providers/ModelProvider';

export function useModels() {
  const ctx = useContext(ModelContext);
  if (!ctx) throw new Error('useModels must be used within ModelProvider');
  return ctx;
}
