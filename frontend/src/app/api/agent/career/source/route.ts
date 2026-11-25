import { NextRequest } from "next/server";
import { discoveryGateway } from "@/lib/server/discovery";

export function POST(request: NextRequest) {
  return discoveryGateway(request, "source");
}
