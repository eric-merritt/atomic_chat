import { useContext } from 'react';
import { WorkspaceContext } from '../providers/WorkspaceProvider';

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error('useWorkspace must be used within WorkspaceProvider');
  return ctx;
}
