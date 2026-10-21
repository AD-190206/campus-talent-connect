"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getSession, SESSION_EXPIRED_EVENT, setSession } from "./api";
import type { Role, SessionUser } from "./types";

type Status = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: Status;
  user: SessionUser | null;
  /** True when the last session ended because tokens could not be refreshed. */
  expired: boolean;
  login: (email: string, password: string) => Promise<SessionUser>;
  logout: () => Promise<void>;
  updateUser: (patch: Partial<SessionUser>) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<SessionUser | null>(null);
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    const session = getSession();
    if (!session?.user) {
      setStatus("anonymous");
      return;
    }
    // Show the stored user immediately, then confirm the session is valid.
    setUser(session.user);
    setStatus("authenticated");
    api.auth
      .me()
      .then(({ data }) => {
        setUser(data);
        setSession({ ...getSession()!, user: data });
      })
      .catch(() => {
        // A 401 that could not be refreshed is handled by the event below;
        // network errors keep the stored session.
      });
  }, []);

  useEffect(() => {
    const onExpired = () => {
      setUser(null);
      setExpired(true);
      setStatus("anonymous");
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await api.auth.login(email, password);
    setSession({ ...data, user: data.user });
    setUser(data.user);
    setExpired(false);
    setStatus("authenticated");
    return data.user;
  }, []);

  const logout = useCallback(async () => {
    const session = getSession();
    setSession(null);
    setUser(null);
    setStatus("anonymous");
    if (session?.refresh_token) {
      await api.auth.logout(session.refresh_token).catch(() => undefined);
    }
  }, []);

  const updateUser = useCallback((patch: Partial<SessionUser>) => {
    setUser((current) => {
      if (!current) return current;
      const next = { ...current, ...patch };
      const session = getSession();
      if (session) setSession({ ...session, user: next });
      return next;
    });
  }, []);

  return (
    <AuthContext.Provider value={{ status, user, expired, login, logout, updateUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** The signed-in user; only call inside the authenticated app layout. */
export function useUser(): SessionUser {
  const { user } = useAuth();
  if (!user) throw new Error("useUser called without a signed-in user");
  return user;
}

export const ROLE_LABEL: Record<Role, string> = {
  STUDENT: "Student",
  CLIENT: "Client",
  ADMIN: "Administrator",
};
