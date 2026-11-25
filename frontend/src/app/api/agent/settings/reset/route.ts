import { rejectWorkspaceSession } from "@/lib/server/workspace-session";
import type { NextRequest } from "next/server";
import { settingsGateway } from "@/lib/server/settings";

export function POST(request: NextRequest) {
  const sessionRejected =
    rejectWorkspaceSession(request);

  if (sessionRejected) return sessionRejected;

  return settingsGateway(request, "reset");
}
