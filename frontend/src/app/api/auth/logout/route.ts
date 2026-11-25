import { NextRequest } from "next/server";

import {
  authBackend,
  authResponse,
  clearSession,
  readSession,
  validSessionBinding,
  rejectAuthRequest,
} from "@/lib/server/auth";

export async function POST(request: NextRequest) {
  const rejected = rejectAuthRequest(request);

  if (rejected) return rejected;

  const token = readSession(request);

  if (token && !validSessionBinding(request, token)) {
    return authResponse(
      { detail: "Workspace session changed" }, 401
    );
  }

  if (token) {
    const response = await authBackend(
      "logout",
      { method: "POST" },
      token
    );

    if (!response.ok && response.status !== 401) {
      return authResponse(
        { detail: "Logout unavailable. Please retry." },
        503
      );
    }
  }

  return clearSession(
    request,
    authResponse({
      authenticated: false,
    })
  );
}
