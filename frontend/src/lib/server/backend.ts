import { NextResponse } from "next/server";

const BACKEND_URL = "http://127.0.0.1:8000";

const LOCAL_ORIGINS = new Set([
  "http://127.0.0.1:3000",
  "http://localhost:3000",
]);

export function rejectRequest(request: Request) {
  if (process.env.AEGIS_LOCAL_BACKEND !== "1") {
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
  endpoint: "/api/v1/status" | "/api/v1/chat" | "/api/v1/inference",
  init: RequestInit = {}
) {
  try {
    const response = await fetch(
      `${BACKEND_URL}${endpoint}`,
      {
        ...init,
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(
          endpoint === "/api/v1/inference" ? 30000 : 5000
        ),
      }
    );

    if (!response.ok) {
      return NextResponse.json(
        { detail: "Backend request rejected" },
        { status: response.status }
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
