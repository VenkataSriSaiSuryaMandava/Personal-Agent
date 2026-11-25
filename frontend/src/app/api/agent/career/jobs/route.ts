import { rejectWorkspaceSession } from "@/lib/server/workspace-session";
import { NextRequest } from "next/server";
import { discoveryGateway } from "@/lib/server/discovery";

export function GET(request: NextRequest) {
  const sessionRejected =
    rejectWorkspaceSession(request);

  if (sessionRejected) return sessionRejected;

  return discoveryGateway(request, "jobs");
}
