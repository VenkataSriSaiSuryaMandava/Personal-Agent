import { NextRequest } from "next/server";

import {
  authBackend,
  authResponse,
  rejectAuthRequest,
  setSession,
} from "@/lib/server/auth";

export async function POST(request: NextRequest) {
  const rejected = rejectAuthRequest(request);

  if (rejected) return rejected;

  const type = request.headers
    .get("content-type")
    ?.split(";")[0]
    .trim()
    .toLowerCase();

  if (type !== "application/json") {
    return authResponse(
      { detail: "JSON request required" },
      415
    );
  }

  let raw = "";
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

  let bytes = 0;

  try {
    while (true) {
      const { done, value } = await reader.read();

      if (done) break;

      bytes += value.byteLength;

      if (bytes > 4096) {
        await reader.cancel();

        return authResponse(
          { detail: "Request too large" },
          413
        );
      }

      raw += decoder.decode(value, {
        stream: true,
      });
    }

    raw += decoder.decode();

    const body = JSON.parse(raw);

    if (
      !body ||
      typeof body !== "object" ||
      Array.isArray(body) ||
      Object.keys(body).length !== 2 ||
      typeof body.username !== "string" ||
      typeof body.password !== "string" ||
      !body.username ||
      !body.password ||
      [...body.username].length > 128 ||
      [...body.password].length > 128
    ) {
      return authResponse(
        { detail: "Invalid credentials format" },
        422
      );
    }

    const response = await authBackend("login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        username: body.username,
        password: body.password,
      }),
    });

    if (response.status === 401) {
      return authResponse(
        { detail: "Invalid username or password" },
        401
      );
    }

    if (response.status === 429) {
      const result = authResponse(
        { detail: "Too many attempts. Try again later." },
        429
      );

      result.headers.set("Retry-After", "900");

      return result;
    }

    if (!response.ok) {
      return authResponse(
        { detail: "Authentication unavailable" },
        503
      );
    }

    const result = await response.json();

    if (
      result.authenticated !== true ||
      typeof result.session_token !== "string" ||
      !/^[A-Za-z0-9_-]{43}$/.test(result.session_token) ||
      result.expires_in !== 43200
    ) {
      return authResponse(
        { detail: "Authentication unavailable" },
        503
      );
    }

    return setSession(
      request,
      authResponse({ authenticated: true }),
      result.session_token
    );
  } catch {
    return authResponse(
      { detail: "Invalid request" },
      422
    );
  } finally {
    reader.releaseLock();
  }
}
