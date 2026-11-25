import type { NextRequest } from "next/server";
import { careerGateway } from "@/lib/server/career";

export function GET(request: NextRequest) {
  return careerGateway(request, "resume");
}

export function POST(request: NextRequest) {
  return careerGateway(request, "resume");
}
