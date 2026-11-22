import type { NextRequest } from "next/server";
import { requireSession, readSession } from "@/lib/server/auth";
import { NextResponse } from "next/server";
import {
  callBackend,
  rejectRequest,
} from "@/lib/server/backend";

export async function POST(request: NextRequest) {
  const rejected = rejectRequest(request);

  if (rejected) return rejected;

  const unauthorized = await requireSession(request);
  if (unauthorized) return unauthorized;


  try {
    const contentType =
      request.headers.get("content-type") ?? "";

    if (!contentType.startsWith("application/json")) {
      return NextResponse.json(
        { detail: "JSON request required" },
        { status: 415 }
      );
    }

    const raw = await request.text();

    if (new TextEncoder().encode(raw).length > 32768) {
      return NextResponse.json(
        { detail: "Request too large" },
        { status: 413 }
      );
    }

    const body = JSON.parse(raw);

    if (
      !body ||
      typeof body !== "object" ||
      Array.isArray(body) ||
      Object.keys(body).length !== 1 ||
      typeof body.message !== "string" ||
      !body.message.trim() ||
      body.message.length > 4000
    ) {
      return NextResponse.json(
        { detail: "Invalid request" },
        { status: 422 }
      );
    }

    return callBackend("/api/v1/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message: body.message.trim(),
      }),
    }, readSession(request) ?? undefined);
  } catch {
    return NextResponse.json(
      { detail: "Invalid request" },
      { status: 400 }
    );
  }
}
