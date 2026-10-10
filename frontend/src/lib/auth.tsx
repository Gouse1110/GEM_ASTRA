/**
 * frontend/src/lib/auth.tsx
 * Auth context — stores the JWT in memory (sessionStorage for tab persistence).
 * The token is never sent to localStorage to reduce XSS exposure.
 */

import {
  createContext, useContext, useState, useEffect,
  useCallback, type ReactNode,
} from "react";
import { fetchMe, login as apiLogin, type UserProfile } from "./api";

interface AuthState {
  token: string | null;
  user: UserProfile | null;
  loading: boolean;
}

interface AuthContext extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthContext | null>(null);

const TOKEN_KEY = "gem_astra_token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    token: null,
    user: null,
    loading: true,
  });

  // Restore session from sessionStorage on mount
  useEffect(() => {
    const stored = sessionStorage.getItem(TOKEN_KEY);
    if (!stored) {
      setState({ token: null, user: null, loading: false });
      return;
    }
    fetchMe(stored)
      .then((user) => setState({ token: stored, user, loading: false }))
      .catch(() => {
        sessionStorage.removeItem(TOKEN_KEY);
        setState({ token: null, user: null, loading: false });
      });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const resp = await apiLogin(email, password);
    sessionStorage.setItem(TOKEN_KEY, resp.access_token);
    const user = await fetchMe(resp.access_token);
    setState({ token: resp.access_token, user, loading: false });
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    setState({ token: null, user: null, loading: false });
  }, []);

  return (
    <Ctx.Provider value={{ ...state, login, logout }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth(): AuthContext {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
