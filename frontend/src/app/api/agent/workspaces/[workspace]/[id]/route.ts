import type { NextRequest } from "next/server";

import {
  workspaceGateway,
} from "@/lib/server/workspaces";

type Context = {
  params: Promise<{
    workspace: string;
    id: string;
  }>;
};

async function handle(
  request: NextRequest,
  context: Context,
) {
  const { workspace, id } =
    await context.params;

  return workspaceGateway(
    request,
    workspace,
    id,
  );
}

export const PATCH = handle;
export const DELETE = handle;
