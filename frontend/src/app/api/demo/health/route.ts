import type { NextRequest } from "next/server";
import { demoBackend, demoResponse } from "@/lib/server/demo";

export async function GET(request: NextRequest) {
  if (request.nextUrl.search) return demoResponse({ detail: "Unexpected query" }, 400);
  return demoBackend("health");
}
