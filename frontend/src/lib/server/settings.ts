import { backendOrigin } from "./backend-origin";
import type { NextRequest } from "next/server";

import {
  authResponse,
  clearSession,
  readSession,
  rejectAuthRequest,
  requireSession,
} from "./auth";

const BACKEND = backendOrigin() + "/api/v1/settings";
const MAX_BODY = 4096;

type Operation =
  | "get"
  | "update"
  | "reset"
  | "providers"
  | "audit"
  | "storage";

const OPERATIONS = {
  get: { method: "GET", suffix: "" },
  update: { method: "PATCH", suffix: "" },
  reset: { method: "POST", suffix: "/reset" },
  providers: { method: "GET", suffix: "/providers" },
  audit: { method: "GET", suffix: "/audit" },
  storage: { method: "GET", suffix: "/storage" },
} as const;

export async function settingsGateway(
  request: NextRequest,
  operation: Operation
) {
  const rejected = rejectAuthRequest(request);

  if (rejected) {
    return authResponse(
      { detail: "Request denied" },
      rejected.status
    );
  }

  const unauthorized = await requireSession(request);

  if (unauthorized) return unauthorized;

  const token = readSession(request);
  const gateway = process.env.AEGIS_GATEWAY_TOKEN;

  if (!token || !gateway || gateway.length < 64) {
    return authResponse(
      { detail: "Gateway unavailable" },
      503
    );
  }

  const config = OPERATIONS[operation];

  if (request.method !== config.method) {
    return authResponse(
      { detail: "Method not allowed" },
      405
    );
  }

  const query = request.nextUrl.search;

  if (
    query.length > 512 ||
    (query && operation !== "audit")
  ) {
    return authResponse(
      { detail: "Invalid query" },
      422
    );
  }

  const headers = new Headers({
    "x-aegis-gateway-token": gateway,
    Authorization: `Bearer ${token}`,
  });

  let raw: string | undefined;

  if (config.method !== "GET") {
    const media = request.headers
      .get("content-type")
      ?.split(";")[0]
      .trim()
      .toLowerCase();

    if (media !== "application/json") {
      return authResponse(
        { detail: "JSON required" },
        415
      );
    }

    const reader = request.body?.getReader();

    if (!reader) {
      return authResponse(
        { detail: "Invalid request" },
        422
      );
    }

    const decoder = new TextDecoder("utf-8", {
      fatal: true,
    });

    let count = 0;
    raw = "";

    try {
      while (true) {
        const { value, done } = await reader.read();

        if (done) break;

        count += value.byteLength;

        if (count > MAX_BODY) {
          await reader.cancel().catch(() => undefined);

          return authResponse(
            { detail: "Request too large" },
            413
          );
        }

        raw += decoder.decode(value, { stream: true });
      }

      raw += decoder.decode();
    } catch {
      return authResponse(
        { detail: "Invalid request" },
        422
      );
    } finally {
      reader.releaseLock();
    }

    headers.set("Content-Type", "application/json");
  }

  try {
    // Preserve the original JSON so the authoritative
    // backend can reject duplicate keys and invalid values.
    const response = await fetch(
      BACKEND + config.suffix + query,
      {
        method: config.method,
        headers,
        body: raw,
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(10000),
      }
    );

    if (response.status === 401) {
      return clearSession(
        request,
        authResponse({ detail: "Session expired" }, 401)
      );
    }

    if (!response.ok) {
      const errors: Record<number, string> = {
        403: "Request denied",
        409: "Settings changed. Reload before saving.",
        413: "Request too large",
        415: "Unsupported content type",
        422: "Invalid or unsupported settings",
        503: "Settings unavailable",
      };

      return authResponse(
        {
          detail:
            errors[response.status] ??
            "Settings request rejected",
        },
        response.status
      );
    }

    const data = await response.json();

    if (!data || typeof data !== "object" ||
        Array.isArray(data)) {
      return authResponse(
        { detail: "Invalid backend response" },
        503
      );
    }

    return authResponse(data);
  } catch {
    return authResponse(
      { detail: "Local settings backend unavailable" },
      503
    );
  }
}
