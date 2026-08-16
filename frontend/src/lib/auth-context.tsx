"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api, type UserPublic } from "./api";

const TOKEN_KEY = "chatagent.token";

interface AuthContextValue {
  token: string | null;
  user: UserPublic | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserPublic | null>(null);
  // Starts true so a page can't flash its logged-out state before localStorage's token
  // (if any) has been checked against the backend.
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // `ignore` guards against setting state after the effect's been cleaned up (React
    // 19 Strict Mode double-invokes this in dev) — the documented pattern for an
    // effect that fetches on mount: https://react.dev/learn/synchronizing-with-effects.
    let ignore = false;

    async function loadStoredSession() {
      const stored = window.localStorage.getItem(TOKEN_KEY);
      if (!stored) {
        if (!ignore) setLoading(false);
        return;
      }
      try {
        const fetchedUser = await api.me(stored);
        if (!ignore) {
          setToken(stored);
          setUser(fetchedUser);
        }
      } catch {
        // Token expired or invalid (backend never returns anything but 401/InvalidToken
        // for a bad token) — treat as logged out rather than leaving a dead token around.
        window.localStorage.removeItem(TOKEN_KEY);
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    loadStoredSession();
    return () => {
      ignore = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { access_token: accessToken } = await api.login(email, password);
    const fetchedUser = await api.me(accessToken);
    window.localStorage.setItem(TOKEN_KEY, accessToken);
    setToken(accessToken);
    setUser(fetchedUser);
  }, []);

  const signup = useCallback(
    async (email: string, password: string) => {
      await api.signup(email, password);
      await login(email, password);
    },
    [login],
  );

  const logout = useCallback(() => {
    window.localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{ token, user, loading, login, signup, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
