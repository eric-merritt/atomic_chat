import { createContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { User } from '../atoms/user';
import { fetchMe, login as apiLogin, register as apiRegister, logout as apiLogout } from '../api/auth';

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  authenticated: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<string | null>;
  register: (username: string, email: string, password: string) => Promise<string | null>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMe().then((res) => {
      if (res.user) setUser(res.user);
      setLoading(false);
    });
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    setError(null);
    const res = await apiLogin(username, password);
    if (res.error) {
      setError(res.error);
      return res.error;
    }
    if (res.user) setUser(res.user);
    return null;
  }, []);

  const register = useCallback(async (username: string, email: string, password: string) => {
    setError(null);
    const res = await apiRegister(username, email, password);
    if (res.error) {
      setError(res.error);
      return res.error;
    }
    if (res.user) setUser(res.user);
    return null;
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{
      user,
      loading,
      authenticated: !!user,
      error,
      login,
      register,
      logout,
    }}>
      {children}
    </AuthContext.Provider>
  );
}
