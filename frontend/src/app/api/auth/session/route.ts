import { NextRequest } from "next/server";
import { publicRuntime } from "@/lib/server/backend";
import { guestSession } from "@/lib/server/backend-origin";
import { readSession, sessionBinding } from "@/lib/server/auth";

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

  const token = readSession(request);

  if (!token) {
    return authResponse(
      { detail: "Authentication required" }, 401
    );
  }

  const response = authResponse({
    authenticated: true,
    role: publicRuntime() || guestSession(readSession(request))
      ? "guest"
      : "owner",
  });

  response.headers.set(
    "x-aegis-session-binding",
    sessionBinding(token)
  );

  return response;
}
