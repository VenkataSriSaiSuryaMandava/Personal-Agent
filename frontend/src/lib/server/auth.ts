import { backendOrigin } from "./backend-origin";
import { NextRequest, NextResponse } from "next/server";
import { rejectRequest } from "./backend";

export const SESSION_COOKIE = "aegis_session";

const SESSION_DURATION = 43200;

const BACKEND_URL = backendOrigin();

const AUTH_HEADERS = {
  "Cache-Control": "no-store",
  "Pragma": "no-cache",
  "X-Content-Type-Options": "nosniff",
};

type AuthEndpoint = "login" | "session" | "logout";

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

  if (!token || !/^[A-Za-z0-9_-]{43}$/.test(token)) {
    return null;
  }

  return token;
}

function cookieOptions(request: NextRequest) {
  return {
    httpOnly: true,
    sameSite: "strict" as const,
    secure: request.nextUrl.protocol === "https:",
    path: "/",
  };
}

export function setSession(
  request: NextRequest,
  response: NextResponse,
  token: string
) {
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
  const rejected = rejectRequest(request);

  if (rejected) return rejected;

  const host = request.headers.get("host");
  const origin = request.headers.get("origin");

  if (origin && origin !== `http://${host}`) {
    return authResponse(
      { detail: "Invalid request origin" },
      403
    );
  }

  return null;
}

export async function authBackend(
  endpoint: AuthEndpoint,
  init: RequestInit = {},
  session?: string
) {
  const gateway = process.env.AEGIS_GATEWAY_TOKEN;

  if (!gateway || gateway.length < 64) {
    return authResponse(
      { detail: "Gateway unavailable" },
      503
    );
  }

  const headers = new Headers(init.headers);

  headers.set("x-aegis-gateway-token", gateway);

  if (session) {
    headers.set("Authorization", `Bearer ${session}`);
  }

  try {
    return await fetch(
      `${BACKEND_URL}/api/v1/auth/${endpoint}`,
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
