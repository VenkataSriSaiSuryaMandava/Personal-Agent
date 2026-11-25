import { NextRequest, NextResponse } from "next/server";

import { backendOrigin } from "./backend-origin";

import {
  authResponse,
  clearSession,
  readSession,
  rejectAuthRequest,
  requireSession,
} from "./auth";

type Endpoint = "profile" | "resumes" | "resume" | "download";

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

const MAX_UPLOAD = 14 * 1024 * 1024;
const MAX_JSON = 2 * 1024 * 1024;
const MAX_DOCUMENT = 10 * 1024 * 1024;

let uploadBusy = false;

function endpointPath(endpoint: Endpoint) {
  switch (endpoint) {
    case "profile":
      return "/api/v1/career/profile";
    case "resumes":
      return "/api/v1/career/resumes";
    case "resume":
      return "/api/v1/career/resume";
    case "download":
      return "/api/v1/career/download";
  }
}

async function boundedBody(
  request: NextRequest,
  limit: number,
) {
  const reader = request.body?.getReader();

  if (!reader) throw new Error("Invalid request");

  const decoder = new TextDecoder("utf-8", {
    fatal: true,
  });

  let body = "";
  let count = 0;

  try {
    while (true) {
      const { value, done } = await reader.read();

      if (done) break;

      count += value.byteLength;

      if (count > limit) {
        await reader.cancel().catch(() => undefined);
        return null;
      }

      body += decoder.decode(value, {
        stream: true,
      });
    }

    return body + decoder.decode();

  } finally {
    reader.releaseLock();
  }
}

export async function careerGateway(
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

  const method = request.method;

  const methods: Record<Endpoint, string[]> = {
    profile: ["GET", "PATCH"],
    resumes: ["GET", "POST"],
    resume: ["GET", "POST"],
    download: ["GET"],
  };

  if (!methods[endpoint].includes(method)) {
    return authResponse(
      { detail: "Method not allowed" }, 405,
    );
  }

  const params = [...request.nextUrl.searchParams.entries()];
  const query = new URLSearchParams();

  if (
    method === "GET" &&
    (endpoint === "resume" || endpoint === "download")
  ) {
    if (
      params.length !== 1 ||
      params[0][0] !== "id" ||
      !UUID.test(params[0][1])
    ) {
      return authResponse(
        { detail: "Invalid document ID" }, 422,
      );
    }

    query.set("id", params[0][1]);

  } else if (params.length) {
    return authResponse(
      { detail: "Invalid query" }, 422,
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

  const upload =
    endpoint === "resumes" && method === "POST";

  if (upload && uploadBusy) {
    return authResponse(
      { detail: "Document upload busy" }, 429,
    );
  }

  if (upload) uploadBusy = true;

  try {
    let body: string | undefined;

    if (method !== "GET") {
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

      let input: string | null;

      try {
        input = await boundedBody(
          request, upload ? MAX_UPLOAD : MAX_JSON,
        );
      } catch {
        return authResponse(
          { detail: "Invalid request" }, 422,
        );
      }

      if (input === null) {
        return authResponse(
          { detail: "Request too large" }, 413,
        );
      }

      body = input;

      headers.set(
        "Content-Type", "application/json",
      );
    }

    const destination = new URL(
      endpointPath(endpoint), backendOrigin(),
    );

    destination.search = query.toString();

    const response = await fetch(destination, {
      method,
      headers,
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(upload ? 25000 : 10000),
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
      const errors: Record<number, string> = {
        403: "Request denied",
        404: "Career record not found",
        409: "Conflict, duplicate document or resume limit reached",
        413: "Document too large",
        415: "Unsupported content type",
        422: "Invalid career request or unsupported document",
        429: "Document parser busy",
        503: "Career storage unavailable",
      };

      return authResponse({
        detail: errors[response.status] ??
          "Career request rejected",
      }, response.status);
    }

    if (endpoint === "download") {
      const length = Number(
        response.headers.get("content-length"),
      );

      const disposition =
        response.headers.get("content-disposition");

      if (
        !Number.isSafeInteger(length) ||
        length < 1 ||
        length > MAX_DOCUMENT ||
        !disposition ||
        !/^attachment; filename="resume\.(pdf|docx|txt)"$/.test(
          disposition,
        )
      ) {
        return authResponse(
          { detail: "Invalid document response" }, 503,
        );
      }

      const bytes = await response.arrayBuffer();

      if (bytes.byteLength !== length) {
        return authResponse(
          { detail: "Invalid document response" }, 503,
        );
      }

      return new NextResponse(bytes, {
        headers: {
          "Content-Type": "application/octet-stream",
          "Content-Disposition": disposition,
          "Cache-Control": "no-store",
          "Pragma": "no-cache",
          "X-Content-Type-Options": "nosniff",
        },
      });
    }

    const result = await response.json();

    if (
      !result || typeof result !== "object" ||
      Array.isArray(result)
    ) {
      return authResponse(
        { detail: "Invalid career response" }, 503,
      );
    }

    return authResponse(result);

  } catch {
    return authResponse(
      { detail: "Career storage unavailable" }, 503,
    );
  } finally {
    if (upload) uploadBusy = false;
  }
}
