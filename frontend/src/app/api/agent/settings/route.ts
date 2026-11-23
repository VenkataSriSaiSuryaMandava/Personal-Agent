import type { NextRequest } from "next/server";
import { settingsGateway } from "@/lib/server/settings";

export function GET(request: NextRequest) {
  return settingsGateway(request, "get");
}

export function PATCH(request: NextRequest) {
  return settingsGateway(request, "update");
}
