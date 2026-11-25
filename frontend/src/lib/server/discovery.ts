import { NextRequest } from "next/server";

import { backendOrigin } from "./backend-origin";

import {
  authResponse,
  clearSession,
  readSession,
  rejectAuthRequest,
  requireSession,
} from "./auth";

type Endpoint = "sources" | "source" | "jobs" | "job" | "match";

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

const MAX_REQUEST = 8192;
const MAX_RESPONSE = 4 * 1024 * 1024;

const METHODS: Record<Endpoint, string[]> = {
  sources: ["GET", "POST"],
  source: ["POST"],
  jobs: ["GET"],
  job: ["GET", "POST"],
  match: ["GET"],
};

function endpointPath(endpoint: Endpoint) {
  switch (endpoint) {
    case "sources":
      return "/api/v1/career/sources";
    case "source":
      return "/api/v1/career/source";
    case "jobs":
      return "/api/v1/career/jobs";
    case "job":
      return "/api/v1/career/job";
    case "match":
      return "/api/v1/career/match";
  }
}

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

function validatedQuery(
  request: NextRequest,
  endpoint: Endpoint,
): URLSearchParams {
  const entries = [
    ...request.nextUrl.searchParams.entries(),
  ];

  const result = new URLSearchParams();

  if (
    request.method === "GET" &&
    (endpoint === "job" || endpoint === "match")
  ) {
    if (
      entries.length !== 1 ||
      entries[0][0] !== "id" ||
      !UUID.test(entries[0][1])
    ) {
      throw new Error("Invalid listing ID");
    }

    result.set("id", entries[0][1]);

    return result;
  }

  if (
    request.method !== "GET" ||
    endpoint !== "jobs"
  ) {
    if (entries.length) {
      throw new Error("Invalid query");
    }

    return result;
  }

  for (const [key, value] of entries) {
    if (result.has(key)) {
      throw new Error("Duplicate query");
    }

    switch (key) {
      case "q":
      case "location":
        if (
          value.length > 200 ||
          /[\p{Cc}\p{Cf}]/u.test(value)
        ) {
          throw new Error("Invalid search");
        }
        break;

      case "freshness":
        if (!["all", "fresh", "stale"].includes(value)) {
          throw new Error("Invalid freshness");
        }
        break;

      case "provider":
        if (
          !["greenhouse", "lever", "ashby"]
            .includes(value)
        ) {
          throw new Error("Invalid provider");
        }
        break;

      case "limit":
      case "offset": {
        if (!/^[0-9]{1,7}$/.test(value)) {
          throw new Error("Invalid pagination");
        }

        const number = Number(value);

        if (
          key === "limit" &&
          (number < 1 || number > 100)
        ) {
          throw new Error("Invalid limit");
        }

        if (
          key === "offset" &&
          number > 1000000
        ) {
          throw new Error("Invalid offset");
        }

        break;
      }

      default:
        throw new Error("Invalid query");
    }

    result.set(key, value);
  }

  return result;
}

export async function discoveryGateway(
  request: NextRequest,
  endpoint: Endpoint,
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

  let query: URLSearchParams;

  try {
    query = validatedQuery(request, endpoint);
  } catch {
    return authResponse(
      { detail: "Invalid discovery query" }, 422,
    );
  }

  const gateway = process.env.AEGIS_GATEWAY_TOKEN;
  const session = readSession(request);

  if (!gateway || gateway.length < 64 || !session) {
    return authResponse(
      { detail: "Gateway unavailable" }, 503,
    );
  }

  const headers = new Headers({
    "x-aegis-gateway-token": gateway,
    Authorization: `Bearer ${session}`,
  });

  let body: string | undefined;

  if (request.method !== "GET") {
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
        MAX_REQUEST,
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

  try {
    const destination = new URL(
      endpointPath(endpoint),
      backendOrigin(),
    );

    destination.search = query.toString();

    const signal = AbortSignal.timeout(
      endpoint === "source" ? 30000 : 10000,
    );

    const response = await fetch(destination, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "error",
      signal,
    });

    if (response.status === 401) {
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
        403: "Request denied",
        404: "Discovery record not found",
        409: "Source changed or limit reached",
        413: "Request too large",
        415: "Unsupported content type",
        422: "Invalid discovery request",
        429: "Discovery operation busy",
        503: "Discovery unavailable",
      };

      return authResponse(
        {
          detail: errors[response.status] ??
            "Discovery unavailable",
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

      throw new Error("Invalid response type");
    }

    const raw = await boundedText(
      response.body,
      MAX_RESPONSE,
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
      { detail: "Discovery unavailable" }, 503,
    );
  }
}
