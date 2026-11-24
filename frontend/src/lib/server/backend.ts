import { backendOrigin } from "./backend-origin";
import { NextResponse } from "next/server";

const BACKEND_URL = backendOrigin();

const LOCAL_ORIGINS = new Set([
  "http://127.0.0.1:3000",
  "http://localhost:3000",
]);

export function rejectRequest(request: Request) {
  if (process.env.AEGIS_PUBLIC_DEMO === "1" || process.env.AEGIS_LOCAL_BACKEND !== "1") {
    return NextResponse.json(
      { detail: "Local backend access is disabled" },
      { status: 403 }
    );
  }

  const host = request.headers.get("host");

  if (host !== "127.0.0.1:3000" && host !== "localhost:3000") {
    return NextResponse.json(
      { detail: "Invalid host" },
      { status: 403 }
    );
  }

  const origin = request.headers.get("origin");

  if (
    (request.method !== "GET" || origin !== null) &&
    !LOCAL_ORIGINS.has(origin ?? "")
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
  const headers = new Headers(init.headers);

  {
    const token = process.env.AEGIS_GATEWAY_TOKEN;

    if (!token || token.length < 64) {
      return NextResponse.json(
        { detail: "Gateway not configured" },
        { status: 503 }
      );
    }

    headers.set("x-aegis-gateway-token", token);
  }

  if (session) {
    headers.set("Authorization", `Bearer ${session}`);
  }

  try {
    const response = await fetch(
      `${BACKEND_URL}${endpoint}`,
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
          503: [
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
