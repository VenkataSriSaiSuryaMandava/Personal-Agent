import { NextRequest } from "next/server";
import { publicRuntime } from "@/lib/server/backend";
import {
  guestAvailable,
  guestSession,
} from "@/lib/server/backend-origin";

import {
  authBackend,
  authResponse,
  readSession,
  inspectSession,
  rejectAuthRequest,
  setSession,
} from "@/lib/server/auth";

export async function POST(request: NextRequest) {
  const rejected = rejectAuthRequest(request);

  if (rejected) return rejected;

  if (!publicRuntime() && !guestAvailable()) {
    return authResponse(
      { detail: "Public sessions unavailable" },
      403
    );
  }

  // An empty POST may still have a readable body stream.
  // Reject actual payload bytes without buffering the body.
  const reader = request.body?.getReader();

  if (reader) {
    try {
      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        if (value.byteLength > 0) {
          await reader.cancel();

          return authResponse(
            { detail: "Unexpected request data" },
            422
          );
        }
      }
    } catch {
      return authResponse(
        { detail: "Invalid request body" },
        422
      );
    } finally {
      reader.releaseLock();
    }
  }

  let existing = readSession(request);

  if (existing && !publicRuntime() && !guestSession(existing)) {
    const status = await inspectSession(existing);

    if (status === "valid") {
      return authResponse(
        { detail: "Sign out before switching access mode" },
        409
      );
    }

    if (status !== "expired") {
      return authResponse(
        { detail: "Session temporarily unavailable" },
        status === "limited" ? 429 : 503
      );
    }

    existing = null;
  }

  // The isolated backend validates the query and session
  // before either resuming or creating a visitor.
  const query = request.nextUrl.searchParams;

  let response = await authBackend(
    "guest",
    { method: "POST" },
    existing ?? undefined,
    query
  );

  if (response.status === 401 && existing) {
    response = await authBackend(
      "guest",
      { method: "POST" },
      undefined,
      query
    );
  }

  if (response.status === 422) {
    return authResponse(
      { detail: "Unexpected request data" },
      422
    );
  }

  if (!response.ok) {
    return authResponse(
      { detail: "Public session temporarily unavailable" },
      response.status === 429 ? 429 : 503
    );
  }

  const result = await response.json().catch(() => null);

  if (
    result?.authenticated !== true ||
    typeof result.session_token !== "string" ||
    !/^[A-Za-z0-9_-]{43}$/.test(result.session_token) ||
    result.expires_in !== 43200
  ) {
    return authResponse(
      { detail: "Authentication unavailable" },
      503
    );
  }

  return setSession(
    request,
    authResponse({ authenticated: true, role: "guest" }),
    publicRuntime()
      ? result.session_token
      : `guest.${result.session_token}`
  );
}
