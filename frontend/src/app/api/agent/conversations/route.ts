import { rejectWorkspaceSession } from "@/lib/server/workspace-session";
import type { NextRequest } from "next/server";
import { historyGateway } from "@/lib/server/conversations";

export function GET(request: NextRequest) {
  const sessionRejected =
    rejectWorkspaceSession(request);

  if (sessionRejected) return sessionRejected;

  return historyGateway(request);
}
