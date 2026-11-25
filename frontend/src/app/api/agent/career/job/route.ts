import { NextRequest } from "next/server";
import { discoveryGateway } from "@/lib/server/discovery";

export function GET(request: NextRequest) {
  return discoveryGateway(request, "job");
}

export function POST(request: NextRequest) {
  return discoveryGateway(request, "job");
}
