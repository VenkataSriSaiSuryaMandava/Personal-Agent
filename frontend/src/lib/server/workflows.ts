import { NextRequest } from "next/server";

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

type Endpoint =
  | "list"
  | "detail"
  | "events"
  | "cancel"
  | "execute";

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

const METHODS: Record<Endpoint, string[]> = {
  list: ["GET", "POST"],
  detail: ["GET"],
  events: ["GET"],
  cancel: ["POST"],
  execute: ["POST"],
};

async function boundedText(
  stream: ReadableStream<Uint8Array> | null,
  limit: number,
  signal: AbortSignal,
): Promise<string> {
  if (!stream) throw new Error("Missing body");

  const reader = stream.getReader();

  const decoder = new TextDecoder("utf-8", {
    fatal: true,
  });

  let result = "";
  let size = 0;

  const abort = () => {
    void reader.cancel().catch(() => undefined);
  };

  signal.addEventListener("abort", abort, {
    once: true,
  });

  try {
    while (true) {
      signal.throwIfAborted();

      const { value, done } = await reader.read();

      signal.throwIfAborted();

      if (done) break;

      size += value.byteLength;

      if (size > limit) {
        void reader.cancel().catch(() => undefined);
        throw new RangeError("Body limit exceeded");
      }

      result += decoder.decode(value, {
        stream: true,
      });
    }

    return result + decoder.decode();
  } finally {
    signal.removeEventListener("abort", abort);
    reader.releaseLock();
  }
}

function queryFor(
  request: NextRequest,
  endpoint: Endpoint,
) {
  const result = new URLSearchParams();

  const allowed =
    request.method !== "GET"
      ? []
      : endpoint === "list"
        ? ["limit", "offset"]
        : endpoint === "events"
          ? ["limit", "after_id"]
          : [];

  for (const [key, value] of
    request.nextUrl.searchParams.entries()
  ) {
    if (
      !allowed.includes(key) ||
      result.has(key) ||
      !/^[0-9]{1,16}$/.test(value)
    ) {
      throw new Error("Invalid query");
    }

    const number = Number(value);

    if (
      !Number.isSafeInteger(number) ||
      number < 0 ||
      (key === "limit" &&
        (number < 1 || number > 100)) ||
      (key === "offset" && number > 1000)
    ) {
      throw new Error("Invalid query");
    }

    result.set(key, value);
  }

  return result;
}

export async function workflowGateway(
  request: NextRequest,
  endpoint: Endpoint,
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

  if (!METHODS[endpoint].includes(request.method)) {
    return authResponse(
      { detail: "Method not allowed" }, 405,
    );
  }

  if (
    endpoint !== "list" &&
    (!id || !UUID.test(id))
  ) {
    return authResponse(
      { detail: "Invalid workflow ID" }, 422,
    );
  }

  let query: URLSearchParams;

  try {
    query = queryFor(request, endpoint);
  } catch {
    return authResponse(
      { detail: "Invalid workflow query" }, 422,
    );
  }

  const session = readSession(request);
  const gateway = sessionGateway(session);

  if (!session || !gateway || gateway.length < 64) {
    return authResponse(
      { detail: "Gateway unavailable" }, 503,
    );
  }

  const headers = new Headers({
    "x-aegis-gateway-token": gateway,
    Authorization: `Bearer ${sessionBearer(session)}`,
  });

  let body: string | undefined;

  if (
    request.method === "POST" &&
    endpoint !== "execute"
  ) {
    const media = request.headers
      .get("content-type")
      ?.split(";")[0].trim().toLowerCase();

    if (
      media !== "application/json" ||
      request.headers.has("content-encoding")
    ) {
      return authResponse(
        { detail: "JSON required" }, 415,
      );
    }

    try {
      body = await boundedText(
        request.body,
        4096,
        AbortSignal.timeout(5000),
      );
    } catch (error) {
      return authResponse(
        { detail: "Invalid request body" },
        error instanceof RangeError ? 413 : 422,
      );
    }

    headers.set("Content-Type", "application/json");
  }

  if (endpoint === "execute") {
    if (request.headers.has("content-encoding")) {
      return authResponse(
        { detail: "Unsupported content encoding" }, 415,
      );
    }

    if (request.body) {
      try {
        const raw = await boundedText(
          request.body,
          0,
          AbortSignal.timeout(5000),
        );

        if (raw.length !== 0) {
          throw new Error("Unexpected execution body");
        }
      } catch {
        return authResponse(
          { detail: "Unexpected execution body" }, 422,
        );
      }
    }
  }

  try {
    const prefix = "/api/v1/workflows";

    let path = prefix;

    if (endpoint !== "list") {
      path += "/" + id;

      if (endpoint !== "detail") {
        path += "/" + endpoint;
      }
    }

    const destination = new URL(
      path,
      sessionBackend(session),
    );

    destination.search = query.toString();

    const signal = AbortSignal.timeout(
      endpoint === "execute" ? 30000 : 10000,
    );

    const response = await fetch(destination, {
      method: request.method,
      headers,
      body,
      signal,
      redirect: "error",
      cache: "no-store",
    });

    if (response.status === 401) {
      void response.body?.cancel().catch(
        () => undefined,
      );

      return clearSession(
        request,
        authResponse(
          { detail: "Session expired" }, 401,
        ),
      );
    }

    if (!response.ok) {
      void response.body?.cancel().catch(
        () => undefined,
      );

      const errors: Record<number, string> = {
        403: "Workflow operation denied",
        404: "Workflow or target not found",
        409: "Workflow changed; reload",
        413: "Request too large",
        415: "Unsupported content type",
        422: "Invalid workflow request",
        429: "Workflow busy or capacity reached",
        503: "Workflow unavailable",
      };

      return authResponse(
        {
          detail: errors[response.status] ??
            "Workflow unavailable",
        },
        errors[response.status]
          ? response.status
          : 503,
      );
    }

    const media = response.headers
      .get("content-type")
      ?.split(";")[0].trim().toLowerCase();

    if (media !== "application/json") {
      void response.body?.cancel().catch(
        () => undefined,
      );

      throw new Error("Invalid response");
    }

    const raw = await boundedText(
      response.body,
      512 * 1024,
      signal,
    );

    const result = JSON.parse(raw);

    if (
      !result ||
      typeof result !== "object" ||
      Array.isArray(result)
    ) {
      throw new Error("Invalid response");
    }

    return authResponse(result);

  } catch {
    return authResponse(
      { detail: "Workflow unavailable" }, 503,
    );
  }
}
