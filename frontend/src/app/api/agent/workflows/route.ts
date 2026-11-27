import { NextRequest } from "next/server";
import { rejectWorkspaceSession } from "@/lib/server/workspace-session";
import { workflowGateway } from "@/lib/server/workflows";


export function GET(request: NextRequest) {
  const sessionRejected =
    rejectWorkspaceSession(request);

  if (sessionRejected) return sessionRejected;

  return workflowGateway(request, "list");
}

export function POST(request: NextRequest) {
  const sessionRejected =
    rejectWorkspaceSession(request);

  if (sessionRejected) return sessionRejected;

  return workflowGateway(request, "list");
}
