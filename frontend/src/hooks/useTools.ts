import { useContext } from 'react';
import { ToolContext } from '../providers/ToolProvider';

export function useTools() {
  const ctx = useContext(ToolContext);
  if (!ctx) throw new Error('useTools must be used within ToolProvider');
  return ctx;
}
