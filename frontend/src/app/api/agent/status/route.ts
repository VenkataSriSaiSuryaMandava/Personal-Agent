import {
  callBackend,
  rejectRequest,
} from "@/lib/server/backend";

export async function GET(request: Request) {
  const rejected = rejectRequest(request);

  if (rejected) return rejected;

  return callBackend("/api/v1/status");
}
