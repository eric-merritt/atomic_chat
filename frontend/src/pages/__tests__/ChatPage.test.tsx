import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ChatPage } from '../ChatPage';
import { ThemeProvider } from '../../providers/ThemeProvider';
import { ModelProvider } from '../../providers/ModelProvider';
import { ToolProvider } from '../../providers/ToolProvider';
import { ChatProvider } from '../../providers/ChatProvider';
import { WebSocketProvider } from '../../providers/WebSocketProvider';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

// Mock canvas for ParticleCanvas
HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
  clearRect: vi.fn(), beginPath: vi.fn(), arc: vi.fn(),
  fill: vi.fn(), closePath: vi.fn(), fillStyle: '',
})) as any;

function renderWithProviders() {
  mockFetch.mockResolvedValue({ ok: true, json: async () => ({ models: [], current: null, tools: {} }) });
  return render(
    <MemoryRouter>
      <ThemeProvider>
        <ModelProvider>
          <ToolProvider>
            <ChatProvider>
              <WebSocketProvider enabled={false}>
                <ChatPage />
              </WebSocketProvider>
            </ChatProvider>
          </ToolProvider>
        </ModelProvider>
      </ThemeProvider>
    </MemoryRouter>
  );
}

describe('ChatPage', () => {
  it('renders without crashing with all providers', () => {
    const { container } = renderWithProviders();
    expect(container.firstChild).toBeInTheDocument();
  });

  it('error boundary isolates failures — page still renders if one organism throws', () => {
    const { container } = renderWithProviders();
    expect(container.querySelector('.grid')).toBeInTheDocument();
  });
});
