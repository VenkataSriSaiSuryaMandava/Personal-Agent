import type { NextRequest } from "next/server";
import { requireSession, readSession } from "@/lib/server/auth";
import { NextResponse } from "next/server";

import {
  callBackend,
  rejectRequest,
} from "@/lib/server/backend";

const allowedPrompts = new Set([
  "general_knowledge",
  "job_search_demo",
  "productivity_demo",
]);

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

    if (new TextEncoder().encode(raw).length > 4096) {
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
      Object.keys(body).length !== 2 ||
      !allowedPrompts.has(body.prompt_id) ||
      body.approved !== true
    ) {
      return NextResponse.json(
        { detail: "Invalid inference request" },
        { status: 422 }
      );
    }

    return callBackend("/api/v1/inference", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        prompt_id: body.prompt_id,
        approved: true,
      }),
    }, readSession(request) ?? undefined);
  } catch {
    return NextResponse.json(
      { detail: "Invalid request" },
      { status: 400 }
    );
  }
}
