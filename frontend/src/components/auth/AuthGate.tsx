"use client";

import {
  useState,
  useEffect,
  type ReactNode,
  type FormEvent,
} from "react";

import {
  Shield,
  LockKeyhole,
  LogOut,
} from "lucide-react";


import { writeWorkspaceLocation } from "@/lib/workspace-location";

import {
  rememberActiveConversation,
} from "@/lib/conversation-location";

const GUEST_SESSION_KEY = "aegis-guest-preview";

function hasGuestSession() {
  try {
    return sessionStorage.getItem(GUEST_SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

function rememberGuestSession(enabled: boolean) {
  try {
    if (enabled) {
      sessionStorage.setItem(GUEST_SESSION_KEY, "1");
    } else {
      sessionStorage.removeItem(GUEST_SESSION_KEY);
    }
  } catch {
    // Guest preference storage is optional.
  }
}

type AuthState =
  | "checking"
  | "locked"
  | "guest"
  | "authenticated"
  | "unavailable";

export default function AuthGate({
  children,
  guestContent,
}: {
  children: ReactNode;
  guestContent: ReactNode;
}) {
  const [state, setState] = useState<AuthState>("checking");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function check() {
      try {
        const response = await fetch("/api/auth/session", {
          cache: "no-store",
          signal: AbortSignal.timeout(12000),
        });

        if (!active) return;

        const body = await response.json();

        if (!active) return;

        setState(
          response.ok && body.authenticated === true
            ? "authenticated"
            : response.status === 401
              ? hasGuestSession() ? "guest" : "locked"
              : "unavailable"
        );
      } catch {
        if (active) setState("unavailable");
      }
    }

    void check();

    function expired() {
      rememberActiveConversation(null);
      rememberGuestSession(false);
      setState("locked");
    }

    window.addEventListener("aegis-session-expired", expired);

    return () => {
      active = false;

      window.removeEventListener(
        "aegis-session-expired",
        expired
      );
    };
  }, []);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (busy) return;

    setBusy(true);
    setError("");

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username,
          password,
        }),
        cache: "no-store",
        signal: AbortSignal.timeout(12000),
      });

      const result = await response.json();

      if (response.ok && result.authenticated === true) {
        rememberGuestSession(false);
        rememberActiveConversation(null);
        writeWorkspaceLocation("overview", "general", true);
        setState("authenticated");
        setUsername("");
      } else {
        setError(
          response.status === 429
            ? "Too many attempts. Please wait before retrying."
            : response.status === 401
              ? "Invalid username or password."
              : "Authentication unavailable."
        );
      }
    } catch {
      setError("Unable to connect to local authentication.");
    } finally {
      setPassword("");
      setBusy(false);
    }
  }

  async function logout() {
    if (busy) return;

    setBusy(true);
    setError("");

    try {
      const response = await fetch("/api/auth/logout", {
        method: "POST",
        cache: "no-store",
        signal: AbortSignal.timeout(12000),
      });

      if (!response.ok) {
        throw new Error("Logout failed");
      }

      rememberActiveConversation(null);
      rememberGuestSession(false);
      setState("locked");
    } catch {
      setError("Logout failed. Please retry.");
    } finally {
      setBusy(false);
    }
  }

  if (state === "guest") {
    return (
      <>
        <div className="aegis-auth-bar">
          <span>
            <Shield size={16} />
            Guest preview · AI disabled
          </span>
          <button
            type="button"
            onClick={() => {
              setError("");
              setPassword("");
              rememberGuestSession(false);
              setState("locked");
            }}
          >
            Back to login
          </button>
        </div>
        {guestContent}
      </>
    );
  }

  if (state === "authenticated") {
    return (
      <>
        <div className="aegis-auth-bar">
          <span>
            <Shield size={16} />
            Owner authenticated
          </span>

          <button onClick={logout} disabled={busy}>
            <LogOut size={16} />
            {busy ? "Signing out..." : "Sign out"}
          </button>
        </div>

        {error && (
          <div role="alert" className="aegis-auth-error">
            {error}
          </div>
        )}

        {children}
      </>
    );
  }

  return (
    <main className="aegis-auth-screen">
      <section className="aegis-auth-card">
        <div className="aegis-auth-icon">
          <Shield size={36} />
        </div>

        <div className="aegis-auth-eyebrow">
          PRIVATE INTELLIGENCE WORKSPACE
        </div>

        <h1>Aegis AI</h1>

        <p>Secure access to your personal assistant.</p>

        {state === "checking" ? (
          <p role="status">Verifying secure session...</p>
        ) : state === "unavailable" ? (
          <>
            <p role="alert">
              Local authentication is unavailable.
            </p>

            <button
              className="aegis-auth-submit"
              onClick={() => window.location.reload()}
            >
              Retry connection
            </button>
          </>
        ) : (
          <form onSubmit={login}>
            <label htmlFor="owner-username">
              Username
            </label>

            <input
              id="owner-username"
              name="username"
              autoComplete="username"
              value={username}
              onChange={(event) =>
                setUsername(event.target.value)
              }
              maxLength={128}
              required
              disabled={busy}
            />

            <label htmlFor="owner-password">
              Password
            </label>

            <input
              id="owner-password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) =>
                setPassword(event.target.value)
              }
              maxLength={128}
              required
              disabled={busy}
            />

            {error && (
              <div role="alert" className="aegis-auth-error">
                {error}
              </div>
            )}

            <button
              type="submit"
              className="aegis-auth-submit"
              disabled={busy}
            >
              <LockKeyhole size={17} />
              {busy ? "Authenticating..." : "Unlock workspace"}
            </button>
          </form>
        )}

        {state === "locked" && (
          <div className="aegis-guest-entry">
            <div className="aegis-guest-divider">
              <span>or</span>
            </div>
            <button
              type="button"
              className="aegis-guest-button"
              disabled={busy}
              onClick={() => {
                setPassword("");
                setError("");
                rememberGuestSession(true);
                rememberActiveConversation(null);
        writeWorkspaceLocation("overview", "general", true);
                setState("guest");
              }}
            >
              Explore as Guest
            </button>
            <p>
              Explore the same workspace interface.
              Private data and live AI require Owner access.
            </p>
          </div>
        )}

        <div className="aegis-auth-footer">
          Owner access requires authentication · Guest preview is restricted
        </div>
      </section>
    </main>
  );
}
