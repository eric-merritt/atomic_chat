import { useContext } from 'react';
import { ModelContext } from '../providers/ModelProvider'; // Ensure this path matches where you saved ModelProvider

export function useModels() {
  const context = useContext(ModelContext);
  if (!context) {
    throw new Error('useModels must be used within a ModelProvider');
  }
  return context;
}