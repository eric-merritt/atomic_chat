import { useContext } from 'react';
import { WebSocketContext } from '../providers/WebSocketProvider';

export function useWebSocket() {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error('useWebSocket must be used within WebSocketProvider');
  return ctx;
}
