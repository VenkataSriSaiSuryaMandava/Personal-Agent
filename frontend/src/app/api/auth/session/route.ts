import { NextRequest } from "next/server";

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
  });
}
