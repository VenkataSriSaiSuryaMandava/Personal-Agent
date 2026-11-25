import type { NextRequest } from "next/server";
import { careerGateway } from "@/lib/server/career";

export function GET(request: NextRequest) {
  return careerGateway(request, "resumes");
}

export function POST(request: NextRequest) {
  return careerGateway(request, "resumes");
}
