import type { NextRequest } from "next/server";
import { authResponse, rejectAuthRequest, requireSession, readSession } from "@/lib/server/auth";
import { callBackend } from "@/lib/server/backend";

export async function POST(request: NextRequest) {
  const rejected = rejectAuthRequest(request);
  if (rejected) return rejected;
  const unauthorized = await requireSession(request);
  if (unauthorized) return unauthorized;

  const media = request.headers.get("content-type")?.split(";")[0].trim().toLowerCase();
  if (media !== "application/json") return authResponse({ detail: "JSON required" }, 415);
  const reader = request.body?.getReader();
  if (!reader) return authResponse({ detail: "Invalid request" }, 422);
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let count = 0;
  let raw = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      count += value.byteLength;
      if (count > 98304) {
        await reader.cancel().catch(() => undefined);
        return authResponse({ detail: "Request too large" }, 413);
      }
      raw += decoder.decode(value, { stream: true });
    }
    raw += decoder.decode();
  } catch {
    return authResponse({ detail: "Invalid request" }, 422);
  } finally {
    reader.releaseLock();
  }
  // The backend is the authoritative validator. Do not rewrite approved text.
  return callBackend("/api/v1/conversation", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: raw,
  }, readSession(request) ?? undefined);
}
