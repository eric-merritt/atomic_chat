import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from './providers/ThemeProvider';
import { ModelProvider } from './providers/ModelProvider';
import { ToolProvider } from './providers/ToolProvider';
import { ChatProvider } from './providers/ChatProvider';
import { WebSocketProvider } from './providers/WebSocketProvider';

function ChatPage() {
  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text)]">
      <p>Agentic Chat — providers wired</p>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <ModelProvider>
          <ToolProvider>
            <ChatProvider>
              <WebSocketProvider enabled={false}>
                <Routes>
                  <Route path="/" element={<ChatPage />} />
                </Routes>
              </WebSocketProvider>
            </ChatProvider>
          </ToolProvider>
        </ModelProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
