import type { NextRequest } from "next/server";
import { historyGateway } from "@/lib/server/conversations";

export function GET(request: NextRequest) {
  return historyGateway(request);
}
