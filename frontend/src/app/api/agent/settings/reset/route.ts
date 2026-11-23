import type { NextRequest } from "next/server";
import { settingsGateway } from "@/lib/server/settings";

export function POST(request: NextRequest) {
  return settingsGateway(request, "reset");
}
