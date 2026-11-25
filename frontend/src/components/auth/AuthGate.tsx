"use client";

import {
  useState,
  useEffect,
  type ReactNode,
  type FormEvent,
} from "react";

import {
  Shield,
  UserRound,
  Eye,
  EyeOff,
  LockKeyhole,
  LogOut,
} from "lucide-react";


import "./auth-screen.css";
import {
  acceptSession,
  clearWorkspaceSession,
  notifySessionChange,
  workspaceFetch,
} from "@/lib/session-client";

import { writeWorkspaceLocation } from "@/lib/workspace-location";

import {
  rememberActiveConversation,
} from "@/lib/conversation-location";

type AuthState =
  | "checking"
  | "locked"
  | "authenticated"
  | "unavailable";

export default function AuthGate({
  children,
  publicMode,
}: {
  children: (guest: boolean) => ReactNode;
  publicMode: boolean;
}) {
  const [state, setState] = useState<AuthState>("checking");
  const [guest, setGuest] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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

        setGuest(body.role === "guest");

        setState(
          response.ok && body.authenticated === true &&
            acceptSession(response) &&
            (body.role === "guest" ||
              (!publicMode && body.role === "owner"))
            ? "authenticated"
            : response.status === 401
              ? "locked"
              : "unavailable"
        );
      } catch {
        if (active) setState("unavailable");
      }
    }

    void check();

    function expired() {
      clearWorkspaceSession();
      rememberActiveConversation(null);
      setState("locked");
    }

    function changed(event: StorageEvent) {
      if (event.key === "aegis-session-change") {
        active = false;
        expired();
        window.location.reload();
      }
    }

    window.addEventListener("storage", changed);
    window.addEventListener("aegis-session-expired", expired);

    return () => {
      active = false;
      window.removeEventListener("storage", changed);

      window.removeEventListener(
        "aegis-session-expired",
        expired
      );
    };
  }, [publicMode]);

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

      if (
        response.ok &&
        result.authenticated === true &&
        result.role === "owner" &&
        acceptSession(response)
      ) {
        notifySessionChange();
          rememberActiveConversation(null);
        writeWorkspaceLocation("overview", "general", true);
        setState("authenticated");
        setGuest(false);
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
      setShowPassword(false);
      setBusy(false);
    }
  }

  async function startPublicSession() {
    if (busy) return;

    setBusy(true);
    setError("");

    try {
      const response = await fetch("/api/auth/guest", {
        method: "POST",
        cache: "no-store",
        signal: AbortSignal.timeout(12000),
      });

      const result = await response.json();

      if (
        response.ok &&
        result.authenticated === true &&
        result.role === "guest" &&
        acceptSession(response)
      ) {
        notifySessionChange();
        setGuest(true);
        rememberActiveConversation(null);
        writeWorkspaceLocation("overview", "general", true);
        setState("authenticated");
      } else {
        setError(
          response.status === 429
            ? "Public workspace is busy. Please try again later."
            : "Unable to start a public session."
        );
      }
    } catch {
      setError("Unable to connect to the public workspace.");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    if (busy) return;

    setBusy(true);
    setError("");

    try {
      const response = await workspaceFetch("/api/auth/logout", {
        method: "POST",
        cache: "no-store",
        signal: AbortSignal.timeout(12000),
      });

      if (!response.ok) {
        throw new Error("Logout failed");
      }

      clearWorkspaceSession();
      notifySessionChange();
      rememberActiveConversation(null);
      setState("locked");
    } catch {
      setError("Logout failed. Please retry.");
    } finally {
      setBusy(false);
    }
  }

  if (state === "authenticated") {
    return (
      <>
        <div className="aegis-auth-bar">
          <span>
            <Shield size={16} />
            {guest
              ? "Guest workspace · AI disabled"
              : "Owner authenticated"}
          </span>

          <button onClick={logout} disabled={busy}>
            <LogOut size={16} />
            {busy
              ? "Signing out..."
              : guest ? "End session" : "Sign out"}
          </button>
        </div>

        {error && (
          <div role="alert" className="aegis-auth-error">
            {error}
          </div>
        )}

        {children(guest)}
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
          {publicMode
            ? "PUBLIC INTELLIGENCE WORKSPACE"
            : "PRIVATE INTELLIGENCE WORKSPACE"}
        </div>

        <h1>Aegis <span>AI</span></h1>

        <p>{publicMode
          ? "Explore the functional Aegis workspace with AI disabled."
          : "Secure access to your personal assistant."}</p>

        {state === "checking" ? (
          <p role="status">Verifying secure session...</p>
        ) : state === "unavailable" ? (
          <>
            <p role="alert">
              Authentication is unavailable.
            </p>

            <button
              className="aegis-auth-submit"
              onClick={() => window.location.reload()}
            >
              Retry connection
            </button>
          </>
        ) : publicMode ? (
          <>
            <p>
              Your workspace is temporary and isolated from other
              visitors. Use sample information rather than sensitive
              personal records.
            </p>
            {error && (
              <div role="alert" className="aegis-auth-error">
                {error}
              </div>
            )}
            <button
              type="button"
              className="aegis-auth-submit"
              disabled={busy}
              onClick={() => void startPublicSession()}
            >
              {busy ? "Starting workspace..." : "Open workspace"}
            </button>
          </>
        ) : (
          <form onSubmit={login}>
            <label htmlFor="owner-username">
              Username
            </label>

            <div className="aegis-auth-field">
              <UserRound size={18} aria-hidden="true" />
              <input
              placeholder="Enter your username"
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

            </div>

            <label htmlFor="owner-password">
              Password
            </label>

            <div className="aegis-auth-field">
              <LockKeyhole size={18} aria-hidden="true" />
              <input
              placeholder="Enter your password"
              id="owner-password"
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              onChange={(event) =>
                setPassword(event.target.value)
              }
              maxLength={128}
              required
              disabled={busy}
            />
              <button
                type="button"
                className="aegis-password-toggle"
                aria-label={showPassword
                  ? "Hide password"
                  : "Show password"}
                aria-pressed={showPassword}
                disabled={busy}
                onClick={() => setShowPassword(value => !value)}
              >
                {showPassword
                  ? <EyeOff size={18} />
                  : <Eye size={18} />}
              </button>
            </div>

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


        {!publicMode && state === "locked" && (
          <div className="aegis-auth-guest">
            <div className="aegis-auth-divider">
              <span>OR</span>
            </div>

            <button
              type="button"
              className="aegis-auth-guest-button"
              disabled={busy}
              onClick={() => void startPublicSession()}
            >
              <UserRound size={18} />
              {busy ? "Please wait..." : "Continue as Guest"}
            </button>

            <p className="aegis-auth-guest-note">
              Temporary isolated workspace · AI disabled
            </p>
          </div>
        )}

        {publicMode && (
          <div className="aegis-auth-footer">
            Temporary session · AI disabled
          </div>
        )}
      </section>
    </main>
  );
}
