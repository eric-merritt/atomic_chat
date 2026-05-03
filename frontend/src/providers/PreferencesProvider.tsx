import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import type { Preferences } from '../atoms/user';
import { updatePreferences as apiUpdatePrefs } from '../api/preferences';
import { useAuth } from '../hooks/useAuth';

const FLUSH_DELAY_MS = 400;

interface PreferencesContextValue {
  preferences: Preferences;
  updatePreferences: ( prefs: Partial<Preferences> ) => Promise<void>;
}

const PreferencesContext = createContext<PreferencesContextValue | null>( null );

const mergePrefs = ( base: Preferences, patch: Partial<Preferences> ): Preferences => ( { ...base, ...patch } );

export function PreferencesProvider( { children }: { children: React.ReactNode } ) {
  const { user } = useAuth();
  const [ preferences, setPreferences ] = useState<Preferences>( {} );
  const pendingPatchRef = useRef<Partial<Preferences>>( {} );
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>( null );

  useEffect( () => {
    if ( user?.preferences ) setPreferences( user.preferences );
  }, [ user ] );

  const flushPendingPatch = useCallback( async () => {
    flushTimerRef.current = null;
    const patch = pendingPatchRef.current;
    pendingPatchRef.current = {};
    if ( Object.keys( patch ).length === 0 ) return;
    try {
      const persisted = await apiUpdatePrefs( patch );
      setPreferences( persisted );
    } catch ( err ) {
      console.error( '[preferences] persist failed — re-queueing patch', err );
      pendingPatchRef.current = mergePrefs( pendingPatchRef.current, patch );
    }
  }, [] );

  const updatePreferences = useCallback( async ( prefs: Partial<Preferences> ) => {
    setPreferences( ( prev ) => mergePrefs( prev, prefs ) );
    pendingPatchRef.current = mergePrefs( pendingPatchRef.current, prefs );
    if ( flushTimerRef.current ) clearTimeout( flushTimerRef.current );
    flushTimerRef.current = setTimeout( flushPendingPatch, FLUSH_DELAY_MS );
  }, [ flushPendingPatch ] );

  useEffect( () => {
    return () => {
      if ( flushTimerRef.current ) {
        clearTimeout( flushTimerRef.current );
        void flushPendingPatch();
      }
    };
  }, [ flushPendingPatch ] );

  return (
    <PreferencesContext.Provider value={ { preferences, updatePreferences } }>
      { children }
    </PreferencesContext.Provider>
  );
}

export function usePreferences() {
  const ctx = useContext( PreferencesContext );
  if ( !ctx ) throw new Error( 'usePreferences must be used within PreferencesProvider' );
  return ctx;
}
