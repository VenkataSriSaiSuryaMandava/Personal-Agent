export type Freshness = "all" | "fresh" | "stale";

export type Provider =
  "greenhouse" | "lever" | "ashby";

export type JobSourceInput = {
  provider: Provider;
  board: string;
  company: string;
  enabled: boolean;
};

export type JobSource = Omit<
  JobSourceInput, "enabled"
> & {
  id: string;
  enabled: number;
  revision: number;
  created_at: number;
  updated_at: number;
  last_attempt_at: number | null;
  last_success_at: number | null;
  last_result: "never" | "success" | "failed" | "limited";
};

export type JobListing = {
  id: string;
  source_id: string;
  external_id: string;
  title: string;
  company: string;
  provider: Provider;
  board: string;
  location: string;
  department: string;
  employment_type: string;
  work_mode: "unknown" | "remote" | "hybrid" | "onsite";
  posting_url: string;
  apply_url: string;
  published_at: number | null;
  first_seen_at: number;
  last_seen_at: number;
  last_success_at: number | null;
  last_result: JobSource["last_result"];
  application_id: string | null;
  stale: boolean;
};

export type JobDetail = JobListing & {
  description: string;
  is_open: number;
};

export type JobPage = {
  jobs: JobListing[];
  next_offset: number | null;
};

export type RefreshReason =
  "provider_unavailable" |
  "response_rejected" |
  "board_limit" |
  "cache_limit";

export type RefreshResult = {
  reason?: RefreshReason;
  result:
    "success" | "cached" | "cooldown" |
    "failed" | "limited";
  count?: number;
  refreshed_at: number | null;
};

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

function validId(id: string) {
  if (!UUID.test(id)) {
    throw new Error("Invalid record ID.");
  }

  return id;
}

function revision(source: JobSource) {
  if (
    !Number.isSafeInteger(source.revision) ||
    source.revision < 1
  ) {
    throw new Error("Invalid source revision.");
  }

  return source.revision;
}

type Endpoint = "sources" | "source" | "jobs" | "job";

function endpointPath(endpoint: Endpoint) {
  switch (endpoint) {
    case "sources":
      return "/api/agent/career/sources";
    case "source":
      return "/api/agent/career/source";
    case "jobs":
      return "/api/agent/career/jobs";
    case "job":
      return "/api/agent/career/job";
  }
}

async function request<T>(
  endpoint: Endpoint,
  method: "GET" | "POST" = "GET",
  payload?: object,
  query?: URLSearchParams,
): Promise<T> {
  const path = endpointPath(endpoint);

  const url = new URL(
    path, window.location.origin,
  );

  if (query) url.search = query.toString();

  if (
    url.origin !== window.location.origin ||
    url.pathname !== path
  ) {
    throw new Error("Invalid discovery endpoint.");
  }

  const response = await fetch(url, {
    method,
    body: payload
      ? JSON.stringify(payload)
      : undefined,
    headers: payload
      ? { "Content-Type": "application/json" }
      : undefined,
    credentials: "same-origin",
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(
      endpoint === "source" ? 40000 : 15000,
    ),
  });

  if (response.status === 401) {
    window.dispatchEvent(
      new Event("aegis-session-expired"),
    );
  }

  if (!response.ok) {
    const messages: Record<number, string> = {
      401: "Session expired.",
      403: "Discovery access denied.",
      404: "Record no longer available.",
      409: "Source changed or limit reached. Refresh and retry.",
      413: "Request too large.",
      415: "Unsupported request type.",
      422: "Invalid discovery request.",
      429: "Refresh busy. Try again shortly.",
      503: "Discovery temporarily unavailable.",
    };

    throw new Error(
      messages[response.status] ??
      "Discovery request failed.",
    );
  }

  return response.json() as Promise<T>;
}

export async function listSources() {
  const data = await request<{
    sources: JobSource[];
  }>("sources");

  return data.sources;
}

export function createSource(input: JobSourceInput) {
  return request<JobSource>(
    "sources", "POST", input,
  );
}

export function updateSource(
  source: JobSource,
  input: JobSourceInput,
) {
  return request<JobSource>("source", "POST", {
    id: validId(source.id),
    action: "update",
    expected_revision: revision(source),
    source: input,
  });
}

export function deleteSource(source: JobSource) {
  return request<{ deleted: boolean }>(
    "source", "POST", {
      id: validId(source.id),
      action: "delete",
      expected_revision: revision(source),
    },
  );
}

export function refreshSource(
  source: JobSource,
  force = false,
) {
  return request<RefreshResult>(
    "source", "POST", {
      id: validId(source.id),
      action: "refresh",
      expected_revision: revision(source),
      force,
    },
  );
}

export function listJobs(
  search = "",
  provider: Provider | "" = "",
  offset = 0,
  location = "",
  freshness: Freshness = "all",
) {
  if (
    !Number.isSafeInteger(offset) ||
    offset < 0 ||
    offset > 1000000
  ) {
    throw new Error("Invalid pagination.");
  }

  const query = new URLSearchParams({
    limit: "50",
    offset: String(offset),
  });

  if (search.trim()) query.set("q", search.trim());

  if (provider) query.set("provider", provider);
  if (location.trim()) query.set("location", location.trim());
  if (freshness !== "all") query.set("freshness", freshness);

  return request<JobPage>(
    "jobs", "GET", undefined, query,
  );
}

export function getJob(id: string) {
  return request<JobDetail>(
    "job",
    "GET",
    undefined,
    new URLSearchParams({
      id: validId(id),
    }),
  );
}

export function saveJob(id: string) {
  return request<{
    application_id: string;
    created: boolean;
  }>("job", "POST", {
    id: validId(id),
  });
}

const LINK_HOSTS: Record<Provider, string[]> = {
  greenhouse: [
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "boards.eu.greenhouse.io",
    "job-boards.eu.greenhouse.io",
  ],
  lever: [
    "jobs.lever.co",
    "jobs.eu.lever.co",
  ],
  ashby: ["jobs.ashbyhq.com"],
};

export function safeJobLink(
  value: string,
  provider: Provider,
  board?: string,
  externalId?: string,
): string | null {
  if (
    typeof value !== "string" ||
    !value ||
    value.length > 2000 ||
    /[\s\\\p{Cc}\p{Cf}]/u.test(value)
  ) {
    return null;
  }

  try {
    const url = new URL(value);

    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      url.port ||
      url.pathname.startsWith("//")
    ) {
      return null;
    }

    if (
      provider === "greenhouse" &&
      board === "stripe" &&
      externalId &&
      /^[0-9]{1,20}$/.test(externalId) &&
      value ===
        "https://stripe.com/jobs/search?gh_jid=" + externalId
    ) {
      return value;
    }

    if (LINK_HOSTS[provider]?.includes(url.hostname)) {
      return url.href;
    }

    if (
      provider === "greenhouse" &&
      board === "stripe" &&
      externalId &&
      /^[0-9]{1,20}$/.test(externalId) &&
      url.hostname === "stripe.com" &&
      !url.hash &&
      /^https:\/\/stripe\.com\//i.test(value) &&
      new RegExp(
        "^/careers/listing/[A-Za-z0-9-]+/" + externalId + "/?$",
      ).test(url.pathname)
    ) {
      return "https://stripe.com" + url.pathname;
    }

    return null;
  } catch {
    return null;
  }
}
