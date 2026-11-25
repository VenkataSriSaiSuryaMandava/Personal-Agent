import { rejectWorkspaceSession } from "@/lib/server/workspace-session";
import type { NextRequest } from "next/server";
import { careerGateway } from "@/lib/server/career";

export function GET(request: NextRequest) {
  const sessionRejected =
    rejectWorkspaceSession(request);

  if (sessionRejected) return sessionRejected;

  return careerGateway(request, "download");
}
