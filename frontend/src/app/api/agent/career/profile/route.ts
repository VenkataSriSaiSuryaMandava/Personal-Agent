import type { NextRequest } from "next/server";
import { careerGateway } from "@/lib/server/career";

export function GET(request: NextRequest) {
  return careerGateway(request, "profile");
}

export function PATCH(request: NextRequest) {
  return careerGateway(request, "profile");
}
