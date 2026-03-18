import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './providers/AuthProvider';
import { ThemeProvider } from './providers/ThemeProvider';
import { ModelProvider } from './providers/ModelProvider';
import { ToolProvider } from './providers/ToolProvider';
import { ChatProvider } from './providers/ChatProvider';
import { WebSocketProvider } from './providers/WebSocketProvider';
import { PreferencesProvider } from './providers/PreferencesProvider';
import { ChatPage } from './pages/ChatPage';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { useAuth } from './hooks/useAuth';

function AuthGate() {
  const { authenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-[var(--bg-base)]">
        <span className="text-[var(--text-muted)] text-sm">Loading...</span>
      </div>
    );
  }

  if (!authenticated) return <LoginPage />;

  return (
    <PreferencesProvider>
      <ModelProvider>
        <ToolProvider>
          <ChatProvider>
            <WebSocketProvider enabled={false}>
              <Routes>
                <Route path="/" element={<ChatPage />} />
                <Route path="/dashboard" element={<DashboardPage />} />
              </Routes>
            </WebSocketProvider>
          </ChatProvider>
        </ToolProvider>
      </ModelProvider>
    </PreferencesProvider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ThemeProvider>
          <AuthGate />
        </ThemeProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
