import { useContext } from 'react';
import { CookieContext } from '../providers/CookieProvider';

export function useCookies() {
  const ctx = useContext(CookieContext);
  if (!ctx) throw new Error('useCookies must be used within CookieProvider');
  return ctx;
}
