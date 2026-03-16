import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { ReactNode } from 'react';
import { WebSocketProvider } from '../../providers/WebSocketProvider';
import { useWebSocket } from '../useWebSocket';

class MockWebSocket {
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  close = vi.fn();
  send(data: string) { this.sent.push(data); }
}

let mockWs: MockWebSocket;

beforeEach(() => {
  mockWs = new MockWebSocket();
  // vi.fn with arrow function can't be used as constructor; use a wrapper class
  vi.stubGlobal('WebSocket', function MockWebSocketConstructor() { return mockWs; });
});

function wrapper({ children }: { children: ReactNode }) {
  return <WebSocketProvider enabled={true}>{children}</WebSocketProvider>;
}

describe('useWebSocket', () => {
  it('connects and sets connected=true on open', () => {
    const { result } = renderHook(() => useWebSocket(), { wrapper });
    expect(result.current.connected).toBe(false);
    act(() => { mockWs.onopen?.(); });
    expect(result.current.connected).toBe(true);
  });

  it('sendToolResult sends correct JSON', () => {
    const { result } = renderHook(() => useWebSocket(), { wrapper });
    act(() => { mockWs.onopen?.(); });
    act(() => { result.current.sendToolResult('tool-1', 'done'); });
    expect(mockWs.sent[0]).toBe(JSON.stringify({ tool_result: { id: 'tool-1', output: 'done' } }));
  });

  it('calls ws.close on unmount', () => {
    const { unmount } = renderHook(() => useWebSocket(), { wrapper });
    unmount();
    expect(mockWs.close).toHaveBeenCalled();
  });
});
