import { NextRequest } from "next/server";
import { publicRuntime } from "@/lib/server/backend";
import { guestSession } from "@/lib/server/backend-origin";
import { readSession } from "@/lib/server/auth";

import {
  authResponse,
  rejectAuthRequest,
  requireSession,
} from "@/lib/server/auth";

export async function GET(request: NextRequest) {
  const rejected = rejectAuthRequest(request);

  if (rejected) return rejected;

  const unauthorized = await requireSession(request);

  if (unauthorized) return unauthorized;

  return authResponse({
    authenticated: true,
    role: publicRuntime() || guestSession(readSession(request))
      ? "guest"
      : "owner",
  });
}
