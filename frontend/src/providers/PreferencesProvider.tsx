import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import type { Preferences } from '../atoms/user';
import { updatePreferences as apiUpdatePrefs } from '../api/preferences';
import { useAuth } from '../hooks/useAuth';

interface PreferencesContextValue {
  preferences: Preferences;
  updatePreferences: (prefs: Partial<Preferences>) => Promise<void>;
}

const PreferencesContext = createContext<PreferencesContextValue | null>(null);

export function PreferencesProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [preferences, setPreferences] = useState<Preferences>({});

  useEffect(() => {
    if (user?.preferences) setPreferences(user.preferences);
  }, [user]);

  const updatePreferences = useCallback(async (prefs: Partial<Preferences>) => {
    const updated = await apiUpdatePrefs(prefs);
    setPreferences(updated);
  }, []);

  return (
    <PreferencesContext.Provider value={{ preferences, updatePreferences }}>
      {children}
    </PreferencesContext.Provider>
  );
}

export function usePreferences() {
  const ctx = useContext(PreferencesContext);
  if (!ctx) throw new Error('usePreferences must be used within PreferencesProvider');
  return ctx;
}
