"use client";

let binding: string | null = null;

export function hasSessionBinding(response: Response) {
  const value = response.headers.get(
    "x-aegis-session-binding"
  );

  return value !== null && /^[a-f0-9]{64}$/.test(value);
}

export function acceptSession(response: Response) {
  const value = response.headers.get(
    "x-aegis-session-binding"
  );

  if (!value || !/^[a-f0-9]{64}$/.test(value)) {
    binding = null;
    return false;
  }

  binding = value;
  return true;
}

export function clearWorkspaceSession() {
  binding = null;
}

export function notifySessionChange() {
  try {
    localStorage.setItem(
      "aegis-session-change",
      crypto.randomUUID()
    );
  } catch {
    // Server-side binding remains mandatory.
  }
}

export async function workspaceFetch(
  input: string | URL,
  init: RequestInit = {}
): Promise<Response> {
  const url = new URL(input, window.location.origin);

  if (
    url.origin !== window.location.origin ||
    (
      !url.pathname.startsWith("/api/agent/") &&
      url.pathname !== "/api/auth/logout"
    )
  ) {
    throw new Error("Invalid workspace request");
  }

  const current = binding;

  if (!current) {
    window.dispatchEvent(
      new Event("aegis-session-expired")
    );
    throw new Error("Workspace session unavailable");
  }

  const headers = new Headers(init.headers);

  headers.set("x-aegis-session-binding", current);

  const response = await fetch(url, {
    ...init,
    headers,
    credentials: "same-origin",
    cache: "no-store",
    redirect: "error",
  });

  if (binding !== current) {
    throw new Error("Workspace session changed");
  }

  if (response.status === 401) {
    clearWorkspaceSession();

    window.dispatchEvent(
      new Event("aegis-session-expired")
    );
  }

  return response;
}
