import type { NextRequest } from "next/server";

import {
  workspaceGateway,
} from "@/lib/server/workspaces";

type Context = {
  params: Promise<{
    workspace: string;
  }>;
};

async function handle(
  request: NextRequest,
  context: Context,
) {
  const { workspace } = await context.params;

  return workspaceGateway(
    request,
    workspace,
  );
}

export const GET = handle;
export const POST = handle;
