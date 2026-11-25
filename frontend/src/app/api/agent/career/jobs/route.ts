import { NextRequest } from "next/server";
import { discoveryGateway } from "@/lib/server/discovery";

export function GET(request: NextRequest) {
  return discoveryGateway(request, "jobs");
}
