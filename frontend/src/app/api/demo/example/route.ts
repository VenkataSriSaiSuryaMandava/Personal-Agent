import type { NextRequest } from "next/server";
import { demoBackend, demoResponse, EXAMPLE_IDS } from "@/lib/server/demo";

export async function GET(request: NextRequest) {
  if (process.env.AEGIS_PUBLIC_DEMO !== "1") {
    return demoResponse({ detail: "Public demo disabled" }, 403);
  }
  const params = [...request.nextUrl.searchParams.entries()];
  const id = EXAMPLE_IDS.find(item => params.length === 1 && params[0][0] === "id" && params[0][1] === item);
  if (!id) return demoResponse({ detail: "Unknown demo example" }, 400);
  return demoBackend(id);
}
