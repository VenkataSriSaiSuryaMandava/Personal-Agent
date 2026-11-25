import {
  guestSession,
  sessionBackend,
  sessionGateway,
  sessionBearer,
} from "./backend-origin";
import { NextResponse } from "next/server";


export function publicRuntime(): boolean {
  return process.env.AEGIS_RUNTIME_MODE === "public";
}

export function publicOrigin(): string | null {
  if (!publicRuntime()) return null;

  const origin =
    process.env.AEGIS_PUBLIC_ORIGIN ??
    "https://aegis-ai-369j.onrender.com";

  const allowed = new Set([
    "https://aegis-ai-369j.onrender.com",
    "http://127.0.0.1:8080",
  ]);

  return allowed.has(origin) ? origin : null;
}

export function rejectRequest(request: Request) {
  const isPublic = publicRuntime();

  if (
    !isPublic &&
    (
      process.env.AEGIS_PUBLIC_DEMO === "1" ||
      process.env.AEGIS_LOCAL_BACKEND !== "1"
    )
  ) {
    return NextResponse.json(
      { detail: "Backend access is disabled" },
      { status: 403 }
    );
  }

  const host = request.headers.get("host");

  let expectedOrigin: string;

  if (isPublic) {
    const configured = publicOrigin();

    if (!configured || host !== new URL(configured).host) {
      return NextResponse.json(
        { detail: "Invalid host" },
        { status: 403 }
      );
    }

    expectedOrigin = configured;
  } else {
    if (
      host !== "127.0.0.1:3000" &&
      host !== "localhost:3000"
    ) {
      return NextResponse.json(
        { detail: "Invalid host" },
        { status: 403 }
      );
    }

    expectedOrigin = `http://${host}`;
  }

  const origin = request.headers.get("origin");

  if (
    (request.method !== "GET" || origin !== null) &&
    origin !== expectedOrigin
  ) {
    return NextResponse.json(
      { detail: "Invalid request origin" },
      { status: 403 }
    );
  }

  return null;
}

export async function callBackend(
  endpoint: "/api/v1/status" | "/api/v1/chat" | "/api/v1/inference" | "/api/v1/conversation",
  init: RequestInit = {},
  session?: string
) {
  if ((publicRuntime() || guestSession(session)) && endpoint !== "/api/v1/status") {
    return NextResponse.json(
      { detail: "AI is disabled in this deployment" },
      {
        status: 403,
        headers: { "Cache-Control": "no-store" },
      }
    );
  }

  const headers = new Headers(init.headers);

  {
    const token = sessionGateway(session);

    if (!token || token.length < 64) {
      return NextResponse.json(
        { detail: "Gateway not configured" },
        { status: 503 }
      );
    }

    headers.set("x-aegis-gateway-token", token);
  }

  if (session) {
    headers.set("Authorization", `Bearer ${sessionBearer(session)}`);
  }

  try {
    const response = await fetch(
      `${sessionBackend(session)}${endpoint}`,
      {
        ...init,
        headers,
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(
          (endpoint === "/api/v1/inference" || endpoint === "/api/v1/conversation") ? 30000 : 5000
        ),
      }
    );

    if (!response.ok) {
      let detail = "Backend request rejected";

      if (endpoint === "/api/v1/conversation") {
        const allowed: Record<number, readonly string[]> = {
          403: ["Conversation denied by policy"],
          429: [
            "Provider quota exceeded",
            "Inference usage limit reached",
          ],
          404: ["Conversation not found"],
          409: [
            "Conversation changed; reload",
            "Conversation retention is disabled",
          ],
          503: [
            "Conversation storage unavailable",
            "Provider temporarily unavailable",
            "Usage storage unavailable",
            "AI unavailable",
          ],
          504: ["Provider request timed out"],
        };

        const body = await response.json().catch(() => null);

        if (
          typeof body?.detail === "string" &&
          allowed[response.status]?.includes(body.detail)
        ) {
          detail = body.detail;
        }
      }

      return NextResponse.json(
        { detail },
        {
          status: response.status,
          headers: { "Cache-Control": "no-store" },
        }
      );
    }

    const data = await response.json();

    return NextResponse.json(data, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      { detail: "Local backend is unavailable" },
      { status: 503 }
    );
  }
}
