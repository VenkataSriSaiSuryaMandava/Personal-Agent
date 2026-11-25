import type { NextRequest } from "next/server";
import { rejectRequest } from "./backend";
import {
  authResponse,
  readSession,
  validSessionBinding,
} from "./auth";

export function rejectWorkspaceSession(
  request: NextRequest
) {
  const rejected = rejectRequest(request);

  if (rejected) return rejected;

  const token = readSession(request);

  if (!token || !validSessionBinding(request, token)) {
    return authResponse(
      { detail: "Workspace session changed or expired" },
      401
    );
  }

  return null;
}
