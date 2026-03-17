import { createContext, useState, useRef, useCallback, useEffect, type ReactNode } from 'react';

interface WebSocketContextValue {
  connected: boolean;
  sendToolResult: (id: string, output: string) => void;
}

export const WebSocketContext = createContext<WebSocketContextValue | null>(null);

interface WebSocketProviderProps {
  children: ReactNode;
  enabled: boolean;
  url?: string;
}

export function WebSocketProvider({ children, enabled, url = '/api/chat/ws' }: WebSocketProviderProps) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!enabled) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}${url}`;
    const ws = new WebSocket(wsUrl);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    wsRef.current = ws;
    return () => { ws.close(); wsRef.current = null; };
  }, [enabled, url]);

  const sendToolResult = useCallback((id: string, output: string) => {
    wsRef.current?.send(JSON.stringify({ tool_result: { id, output } }));
  }, []);

  return (
    <WebSocketContext.Provider value={{ connected, sendToolResult }}>
      {children}
    </WebSocketContext.Provider>
  );
}
