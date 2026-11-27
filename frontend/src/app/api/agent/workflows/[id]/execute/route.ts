import { NextRequest } from "next/server";
import { rejectWorkspaceSession } from "@/lib/server/workspace-session";
import { workflowGateway } from "@/lib/server/workflows";


export async function POST(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const sessionRejected =
    rejectWorkspaceSession(request);

  if (sessionRejected) return sessionRejected;

  const { id } = await context.params;

  return workflowGateway(request, "execute", id);
}
