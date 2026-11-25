import { rejectWorkspaceSession } from "@/lib/server/workspace-session";
import type { NextRequest } from "next/server";
import { historyGateway } from "@/lib/server/conversations";

type Context = {
  params: Promise<{ id: string }>;
};

async function handle(
  request: NextRequest,
  context: Context,
) {
  const sessionRejected =
    rejectWorkspaceSession(request);

  if (sessionRejected) return sessionRejected;

  const { id } = await context.params;

  return historyGateway(request, id);
}

export const GET = handle;
export const PATCH = handle;
export const DELETE = handle;
