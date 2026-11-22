import type { NextRequest } from "next/server";
import { requireSession, readSession } from "@/lib/server/auth";
import {
  callBackend,
  rejectRequest,
} from "@/lib/server/backend";

export async function GET(request: NextRequest) {
  const rejected = rejectRequest(request);

  if (rejected) return rejected;

  const unauthorized = await requireSession(request);
  if (unauthorized) return unauthorized;


  return callBackend("/api/v1/status", {}, readSession(request) ?? undefined);
}
