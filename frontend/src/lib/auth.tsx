import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api } from "@/lib/api";
import { getStoredToken, setStoredToken } from "@/lib/auth-token";

export type AuthUser = {
  id: string;
  email: string;
  display_name?: string | null;
};

export type AuthSession = {
  access_token: string;
  user: AuthUser;
};

type AuthResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

export type AuthContextValue = {
  session: AuthSession | null;
  user: AuthUser | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<{ error: Error | null }>;
  signUp: (email: string, password: string) => Promise<{ error: Error | null }>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const token = getStoredToken();

    if (!token) {
      setLoading(false);
      return;
    }

    api
      .get<AuthUser>("/auth/me")
      .then((user) => {
        if (!active) return;
        setSession({ access_token: token, user });
      })
      .catch(() => {
        if (!active) return;
        setStoredToken(null);
        setSession(null);
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const signIn = useCallback(
    async (
      email: string,
      password: string,
    ): Promise<{ error: Error | null }> => {
      try {
        const response = await api.post<AuthResponse>(
          "/auth/login",
          { email, password },
          { auth: false },
        );
        setStoredToken(response.access_token);
        setSession({
          access_token: response.access_token,
          user: response.user,
        });
        return { error: null };
      } catch (err) {
        return { error: err instanceof Error ? err : new Error(String(err)) };
      }
    },
    [],
  );

  const signUp = useCallback(
    async (
      email: string,
      password: string,
    ): Promise<{ error: Error | null }> => {
      try {
        const response = await api.post<AuthResponse>(
          "/auth/register",
          { email, password },
          { auth: false },
        );
        setStoredToken(response.access_token);
        setSession({
          access_token: response.access_token,
          user: response.user,
        });
        return { error: null };
      } catch (err) {
        return { error: err instanceof Error ? err : new Error(String(err)) };
      }
    },
    [],
  );

  const signOut = useCallback(async (): Promise<void> => {
    try {
      await api.post("/auth/logout", undefined, { auth: false });
    } catch {
      // Ignore network failure on logout
    } finally {
      setStoredToken(null);
      setSession(null);
    }
  }, []);

  const value = useMemo(
    () => ({
      session,
      user: session?.user ?? null,
      loading,
      signIn,
      signUp,
      signOut,
    }),
    [session, loading, signIn, signUp, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }

  return context;
}
