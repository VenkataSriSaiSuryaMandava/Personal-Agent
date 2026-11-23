import { NextResponse } from "next/server";

export const EXAMPLE_IDS = ["search", "systems", "project"] as const;
export type ExampleId = typeof EXAMPLE_IDS[number];

const PATHS = {
  health: "/health",
  search: "/example?id=search",
  systems: "/example?id=systems",
  project: "/example?id=project",
} as const;

export function demoResponse(body: object, status = 200) {
  return NextResponse.json(body, {
    status,
    headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" },
  });
}

export async function demoBackend(endpoint: keyof typeof PATHS) {
  if (process.env.AEGIS_PUBLIC_DEMO !== "1") {
    return demoResponse({ detail: "Public demo disabled" }, 403);
  }
  try {
    const result = await fetch(`http://127.0.0.1:8000${PATHS[endpoint]}`, {
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(2500),
    });
    if (!result.ok) throw new Error("Demo backend unavailable");
    const body = await result.json();
    if (endpoint === "health") {
      if (body?.status !== "ok" || body?.mode !== "public_demo") throw new Error("Invalid health response");
      return demoResponse({ status: "ok", mode: "public_demo" });
    }
    if (body?.mode !== "recorded_demo" || typeof body.prompt !== "string" ||
        typeof body.answer !== "string" || !body.answer || body.answer.length > 12000) {
      throw new Error("Invalid example response");
    }
    return demoResponse({ mode: "recorded_demo", prompt: body.prompt, answer: body.answer });
  } catch {
    return demoResponse({ detail: "Demo temporarily unavailable" }, 503);
  }
}
