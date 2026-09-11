import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Api, loadSession, saveSession } from '../services/api';
import type { Role, Session, User } from '../types';

interface AuthCtx { user: User | null; session: Session | null; login: (email: string, password: string) => Promise<Session>; logout: () => Promise<void>; can: (min: Role) => boolean }
const Ctx = createContext<AuthCtx | null>(null);
const RANK: Record<Role, number> = { VIEWER: 1, ANALYST: 2, ADMIN: 3 };

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => loadSession());
  useEffect(() => {
    const h = () => setSession(null);
    window.addEventListener('tsi-logout', h);
    return () => window.removeEventListener('tsi-logout', h);
  }, []);
  const login = useCallback(async (email: string, password: string) => {
    const s = await Api.login(email, password);
    saveSession(s);
    setSession(s);
    return s;
  }, []);
  const logout = useCallback(async () => {
    const s = loadSession();
    try { if (s) await Api.logout(s.refresh_token); } catch { /* ignore */ }
    saveSession(null);
    setSession(null);
  }, []);
  const can = useCallback((min: Role) => !!session && RANK[session.user.role] >= RANK[min], [session]);
  const value = useMemo(() => ({ user: session?.user ?? null, session, login, logout, can }), [session, login, logout, can]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAuth outside AuthProvider');
  return v;
}
