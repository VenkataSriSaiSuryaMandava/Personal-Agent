import type { NextRequest } from "next/server";

import {
  sessionBackend,
  sessionGateway,
  sessionBearer,
} from "./backend-origin";

import {
  authResponse,
  clearSession,
  readSession,
  rejectAuthRequest,
  requireSession,
} from "./auth";

const BASE = "/api/v1/workspaces";

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export async function workspaceGateway(
  request: NextRequest,
  workspace: string,
  id?: string,
) {
  const rejected = rejectAuthRequest(request);

  if (rejected) {
    return authResponse(
      { detail: "Request denied" },
      rejected.status,
    );
  }

  const unauthorized = await requireSession(request);

  if (unauthorized) return unauthorized;

  const method = request.method;

  if (
    !["GET", "POST", "PATCH", "DELETE"].includes(method) ||
    (!id && !["GET", "POST"].includes(method)) ||
    (id && !["PATCH", "DELETE"].includes(method)) ||
    (workspace === "summary" && method !== "GET")
  ) {
    return authResponse(
      { detail: "Method not allowed" },
      405,
    );
  }

  if (![
    "summary", "tasks", "jobs", "email",
    "calendar", "research", "coding",
    "browser", "memory", "approvals",
  ].includes(workspace)) {
    return authResponse(
      { detail: "Invalid workspace" }, 422,
    );
  }

  if (id !== undefined && !UUID.test(id)) {
    return authResponse(
      { detail: "Invalid record ID" },
      422,
    );
  }

  const query = request.nextUrl.search;

  if (query.length > 512 || (id && query && method !== "DELETE")) {
    return authResponse(
      { detail: "Invalid query" },
      422,
    );
  }

  const session = readSession(request);
  const gateway = sessionGateway(session);

  if (!session || !gateway || gateway.length < 64) {
    return authResponse(
      { detail: "Gateway unavailable" },
      503,
    );
  }

  const headers = new Headers({
    "x-aegis-gateway-token": gateway,
    Authorization: `Bearer ${sessionBearer(session)}`,
  });

  let body: string | undefined;

  if (method === "PATCH" || method === "POST") {
    const media = request.headers
      .get("content-type")
      ?.split(";")[0]
      .trim()
      .toLowerCase();

    if (media !== "application/json") {
      return authResponse(
        { detail: "JSON required" },
        415,
      );
    }

    const reader = request.body?.getReader();

    if (!reader) {
      return authResponse(
        { detail: "Invalid request" },
        422,
      );
    }

    const decoder = new TextDecoder(
      "utf-8",
      { fatal: true },
    );

    let count = 0;
    body = "";

    try {
      while (true) {
        const { value, done } = await reader.read();

        if (done) break;

        count += value.byteLength;

        if (count > 65536) {
          await reader.cancel().catch(() => undefined);

          return authResponse(
            { detail: "Request too large" },
            413,
          );
        }

        body += decoder.decode(
          value,
          { stream: true },
        );
      }

      body += decoder.decode();

    } catch {
      return authResponse(
        { detail: "Invalid request" },
        422,
      );
    } finally {
      reader.releaseLock();
    }

    headers.set(
      "Content-Type",
      "application/json",
    );
  }

  try {
    const response = await fetch(
      sessionBackend(session) + BASE + "/" + workspace + (id ? "/" + id : "") + query,
      {
        method,
        headers,
        body,
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(10000),
      },
    );

    if (response.status === 401) {
      return clearSession(
        request,
        authResponse(
          { detail: "Session expired" },
          401,
        ),
      );
    }

    if (!response.ok) {
      const errors: Record<number, string> = {
        403: "Request denied",
        404: "Record not found",
        409: "Record changed; reload",
        422: "Invalid workspace request",
        503: "Workspace storage unavailable",
      };

      return authResponse(
        {
          detail:
            errors[response.status] ??
            "Workspace request rejected",
        },
        response.status,
      );
    }

    const data = await response.json();

    if (!data || typeof data !== "object" ||
        Array.isArray(data)) {
      return authResponse(
        { detail: "Invalid workspace response" },
        503,
      );
    }

    return authResponse(data);

  } catch {
    return authResponse(
      { detail: "Workspace storage unavailable" },
      503,
    );
  }
}
