import { createHmac, timingSafeEqual } from "node:crypto";
import {
  guestAvailable,
  guestSession,
  sessionBackend,
  sessionGateway,
  sessionBearer,
} from "./backend-origin";
import { NextRequest, NextResponse } from "next/server";
import { rejectRequest, publicRuntime, publicOrigin } from "./backend";

export const SESSION_COOKIE = "aegis_session";

const SESSION_DURATION = 43200;


const AUTH_HEADERS = {
  "Cache-Control": "no-store",
  "Pragma": "no-cache",
  "X-Content-Type-Options": "nosniff",
};

type AuthEndpoint = "login" | "session" | "logout" | "guest";

export function authResponse(
  payload: object,
  status = 200
) {
  return NextResponse.json(payload, {
    status,
    headers: AUTH_HEADERS,
  });
}

export function readSession(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE)?.value;

  if (!token || !/^(?:guest\.)?[A-Za-z0-9_-]{43}$/.test(token)) {
    return null;
  }

  if (guestSession(token) &&
      (publicRuntime() || !guestAvailable())) {
    return null;
  }

  return token;
}

export function sessionBinding(token: string): string {
  const gateway = sessionGateway(token);

  if (!gateway || gateway.length < 64) {
    throw new Error("Session verification unavailable");
  }

  return createHmac("sha256", gateway)
    .update("aegis-workspace-session-v1:")
    .update(token)
    .digest("hex");
}

export function validSessionBinding(
  request: NextRequest,
  token: string
): boolean {
  const supplied = request.headers.get("x-aegis-session-binding");

  if (!supplied || !/^[a-f0-9]{64}$/.test(supplied)) {
    return false;
  }

  try {
    return timingSafeEqual(
      Buffer.from(supplied, "hex"),
      Buffer.from(sessionBinding(token), "hex")
    );
  } catch {
    return false;
  }
}

export async function inspectSession(token: string) {
  const response = await authBackend(
    "session",
    { method: "GET" },
    token
  );

  if (response.status === 401) return "expired" as const;
  if (response.status === 429) return "limited" as const;
  if (!response.ok) return "unavailable" as const;

  const body = await response.json().catch(() => null);

  return body?.authenticated === true
    ? "valid" as const
    : "unavailable" as const;
}

function cookieOptions(request: NextRequest) {
  return {
    httpOnly: true,
    sameSite: "strict" as const,
    secure: publicRuntime()
      ? publicOrigin()?.startsWith("https://") !== false
      : request.nextUrl.protocol === "https:",
    path: "/",
  };
}

export function setSession(
  request: NextRequest,
  response: NextResponse,
  token: string
) {
  response.headers.set(
    "x-aegis-session-binding",
    sessionBinding(token)
  );

  response.cookies.set(SESSION_COOKIE, token, {
    ...cookieOptions(request),
    maxAge: SESSION_DURATION,
  });

  return response;
}

export function clearSession(
  request: NextRequest,
  response: NextResponse
) {
  response.cookies.set(SESSION_COOKIE, "", {
    ...cookieOptions(request),
    maxAge: 0,
  });

  return response;
}

export function rejectAuthRequest(request: NextRequest) {
  return rejectRequest(request);
}

export async function authBackend(
  endpoint: AuthEndpoint,
  init: RequestInit = {},
  session?: string,
  query?: URLSearchParams
) {
  const gateway = sessionGateway(endpoint === "guest" && !publicRuntime() ? "guest." : session);

  if (!gateway || gateway.length < 64) {
    return authResponse(
      { detail: "Gateway unavailable" },
      503
    );
  }

  const headers = new Headers(init.headers);

  headers.set("x-aegis-gateway-token", gateway);

  if (session) {
    headers.set("Authorization", `Bearer ${sessionBearer(session)}`);
  }

  try {
    const destination =
      endpoint === "guest" && !publicRuntime()
        ? sessionBackend("guest.")
        : sessionBackend(session);

    const url = new URL(
      `/api/v1/auth/${endpoint}`,
      destination
    );

    if (query && endpoint === "guest") {
      url.search = query.toString();
    }

    return await fetch(
      url,
      {
        ...init,
        headers,
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(10000),
      }
    );
  } catch {
    return authResponse(
      { detail: "Authentication unavailable" },
      503
    );
  }
}

export async function requireSession(
  request: NextRequest
) {
  const token = readSession(request);

  if (!token) {
    return authResponse(
      { detail: "Authentication required" },
      401
    );
  }

  const response = await authBackend(
    "session",
    { method: "GET" },
    token
  );

  if (response.status === 401) {
    return clearSession(
      request,
      authResponse(
        { detail: "Session expired" },
        401
      )
    );
  }

  if (!response.ok) {
    return authResponse(
      { detail: "Authentication unavailable" },
      503
    );
  }

  const body = await response.json().catch(() => null);

  if (body?.authenticated !== true) {
    return authResponse(
      { detail: "Authentication unavailable" },
      503
    );
  }

  return null;
}
