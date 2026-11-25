import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { backendOrigin } from "@/lib/server/backend-origin";
import { publicRuntime } from "@/lib/server/backend";

function reply(body: object, status = 200) {
  return NextResponse.json(body, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export async function GET(request: NextRequest) {
  if (request.nextUrl.search) {
    return reply({ detail: "Unexpected query" }, 400);
  }

  if (!publicRuntime()) {
    return reply({ detail: "Public runtime disabled" }, 403);
  }

  try {
    const response = await fetch(
      `${backendOrigin()}/health`,
      {
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(2500),
      }
    );

    const body = await response.json();

    if (
      !response.ok ||
      body?.status !== "ok" ||
      body?.mode !== "public"
    ) {
      return reply({ detail: "Backend unavailable" }, 503);
    }

    return reply({ status: "ok", mode: "public" });
  } catch {
    return reply({ detail: "Backend unavailable" }, 503);
  }
}
