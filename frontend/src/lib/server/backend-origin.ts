/**
 * Server-only backend destination.
 *
 * The address is fixed at deployment time, never supplied by
 * a browser request. No arbitrary remote destinations are allowed.
 */
export function backendOrigin(): string {
  const configured =
    process.env.AEGIS_INTERNAL_BACKEND_URL ??
    "http://127.0.0.1:8000";

  if (
    configured !== "http://127.0.0.1:8000" &&
    configured !== "http://backend:8000"
  ) {
    throw new Error(
      "Unsupported internal backend configuration"
    );
  }

  return configured;
}


export function guestSession(session?: string | null): boolean {
  return session?.startsWith("guest.") === true;
}

export function guestAvailable(): boolean {
  return process.env.AEGIS_GUEST_BACKEND_URL ===
    "http://guest-backend:8000";
}

export function sessionBackend(session?: string | null): string {
  if (!guestSession(session)) return backendOrigin();

  if (!guestAvailable()) {
    throw new Error("Guest backend unavailable");
  }

  return "http://guest-backend:8000";
}

export function sessionBearer(session: string): string {
  return guestSession(session) ? session.slice(6) : session;
}


export function sessionGateway(session?: string | null) {
  return guestSession(session)
    ? process.env.AEGIS_GUEST_GATEWAY_TOKEN
    : process.env.AEGIS_GATEWAY_TOKEN;
}
