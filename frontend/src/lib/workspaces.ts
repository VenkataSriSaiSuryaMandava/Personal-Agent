import { workspaceFetch } from "@/lib/session-client";
import type {
  Workspace,
} from "./navigation";

export type RecordWorkspace = Exclude<
  Workspace,
  "overview" | "chat" | "settings"
>;

export type RecordInput = {
  title: string;
  detail: string;
  notes: string;
  status: string;
  reference: string;
  scheduled_at: string;
  priority: "low" | "normal" | "high";
};

export type WorkspaceRecord = RecordInput & {
  id: string;
  workspace: RecordWorkspace;
  revision: number;
  created_at: number;
  updated_at: number;
};

export type WorkspaceCounts = Record<
  RecordWorkspace,
  number
>;

export const WORKSPACE_CONFIG = {
  tasks: {
    title: "Task",
    detail: "Category",
    reference: "Reference",
    statuses: ["todo", "in_progress", "completed"],
    description: "Plan and track your personal tasks.",
  },
  jobs: {
    title: "Job title",
    detail: "Company",
    reference: "Job posting URL",
    statuses: [
      "saved", "applied", "interview",
      "offer", "rejected", "withdrawn",
    ],
    description: "Track applications and interview progress.",
  },
  email: {
    title: "Subject",
    detail: "Recipient",
    reference: "Reference",
    statuses: ["draft", "archived"],
    description: "Prepare local drafts. No emails are sent.",
  },
  calendar: {
    title: "Event",
    detail: "Location",
    reference: "Meeting reference",
    statuses: ["planned", "completed", "cancelled"],
    description: "Manage local events without calendar synchronization.",
  },
  research: {
    title: "Research topic",
    detail: "Category",
    reference: "Source URL",
    statuses: ["planned", "in_progress", "completed"],
    description: "Organize research topics, sources and findings.",
  },
  coding: {
    title: "Project or coding task",
    detail: "Technology",
    reference: "Repository URL",
    statuses: ["planned", "in_progress", "completed"],
    description: "Organize coding work without executing commands.",
  },
  browser: {
    title: "Bookmark or browser task",
    detail: "Purpose",
    reference: "Website URL",
    statuses: ["saved", "reviewed", "archived"],
    description: "Save links and planned actions. Automation is disabled.",
  },
  memory: {
    title: "Memory title",
    detail: "Category",
    reference: "Source",
    statuses: ["active", "archived"],
    description: "Explicitly save local memories. Nothing is automatically sent to AI.",
  },
  approvals: {
    title: "Proposed action",
    detail: "Action category",
    reference: "Reference",
    statuses: ["pending", "approved", "rejected"],
    description: "Record decisions manually. Approval does not authorize execution.",
  },
} satisfies Record<
  RecordWorkspace,
  {
    title: string;
    detail: string;
    reference: string;
    statuses: string[];
    description: string;
  }
>;

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

function collectionEndpoint(
  workspace: RecordWorkspace | "summary",
): string {
  switch (workspace) {
    case "tasks":
      return "/api/agent/workspaces/tasks";
    case "jobs":
      return "/api/agent/workspaces/jobs";
    case "email":
      return "/api/agent/workspaces/email";
    case "calendar":
      return "/api/agent/workspaces/calendar";
    case "research":
      return "/api/agent/workspaces/research";
    case "coding":
      return "/api/agent/workspaces/coding";
    case "browser":
      return "/api/agent/workspaces/browser";
    case "memory":
      return "/api/agent/workspaces/memory";
    case "approvals":
      return "/api/agent/workspaces/approvals";
    case "summary":
      return "/api/agent/workspaces/summary";
    default:
      throw new Error("Invalid workspace.");
  }
}

function recordIdentifier(id: string): string {
  if (
    typeof id !== "string" ||
    !UUID_PATTERN.test(id)
  ) {
    throw new Error("Invalid record identifier.");
  }

  return encodeURIComponent(id);
}

function validOffset(offset: number): number {
  if (
    !Number.isSafeInteger(offset) ||
    offset < 0 ||
    offset > 1000000
  ) {
    throw new Error("Invalid pagination offset.");
  }

  return offset;
}

function validRevision(revision: number): number {
  if (
    !Number.isSafeInteger(revision) ||
    revision < 1
  ) {
    throw new Error("Invalid record revision.");
  }

  return revision;
}

type WorkspaceOperation =
  | {
      kind: "summary";
    }
  | {
      kind: "list";
      workspace: RecordWorkspace;
      offset: number;
    }
  | {
      kind: "create";
      workspace: RecordWorkspace;
      input: RecordInput;
    }
  | {
      kind: "update";
      workspace: RecordWorkspace;
      id: string;
      revision: number;
      input: RecordInput;
    }
  | {
      kind: "delete";
      workspace: RecordWorkspace;
      id: string;
      revision: number;
    };

async function request<T>(
  operation: WorkspaceOperation,
): Promise<T> {
  const endpoint = collectionEndpoint(
    operation.kind === "summary"
      ? "summary"
      : operation.workspace,
  );

  let pathname = endpoint;

  const query = new URLSearchParams();

  let method: "GET" | "POST" | "PATCH" | "DELETE" =
    "GET";

  let body: string | undefined;

  switch (operation.kind) {
    case "summary":
      break;

    case "list":
      query.set("limit", "100");
      query.set(
        "offset",
        String(validOffset(operation.offset)),
      );
      break;

    case "create":
      method = "POST";
      body = JSON.stringify(operation.input);
      break;

    case "update":
      method = "PATCH";

      pathname += "/" + recordIdentifier(
        operation.id,
      );

      body = JSON.stringify({
        ...operation.input,
        expected_revision: validRevision(
          operation.revision,
        ),
      });
      break;

    case "delete":
      method = "DELETE";

      pathname += "/" + recordIdentifier(
        operation.id,
      );

      query.set(
        "revision",
        String(validRevision(operation.revision)),
      );
      break;

    default:
      throw new Error("Invalid workspace operation.");
  }

  const url = new URL(
    endpoint,
    window.location.origin,
  );

  url.pathname = pathname;
  url.search = query.toString();

  if (
    url.origin !== window.location.origin ||
    (
      url.pathname !== endpoint &&
      !url.pathname.startsWith(endpoint + "/")
    )
  ) {
    throw new Error("Invalid workspace endpoint.");
  }

  const response = await workspaceFetch(url, {
    method,
    body,
    headers: body === undefined
      ? undefined
      : { "Content-Type": "application/json" },
    credentials: "same-origin",
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(15000),
  });

  if (response.status === 401) {
    window.dispatchEvent(
      new Event("aegis-session-expired"),
    );
  }

  if (!response.ok) {
    const messages: Record<number, string> = {
      401: "Session expired.",
      403: "Workspace access denied.",
      404: "Record no longer exists.",
      409: "Record changed. Refresh and try again.",
      422: "Invalid record. Review the fields.",
      503: "Workspace storage unavailable.",
    };

    throw new Error(
      messages[response.status] ??
      "Workspace request failed.",
    );
  }

  return response.json() as Promise<T>;
}

export function listRecords(
  workspace: RecordWorkspace,
  offset = 0,
) {
  return request<{
    records: WorkspaceRecord[];
    next_offset: number | null;
  }>({
    kind: "list",
    workspace,
    offset,
  });
}

export type WorkspaceSummaryData = {
  counts: WorkspaceCounts;
  statuses: Record<RecordWorkspace, Record<string, number>>;
  storage: {
    memory_payload_bytes: number;
    conversation_count: number;
    database_page_bytes: number;
  };
};

export function getWorkspaceCounts() {
  return request<WorkspaceSummaryData>({
    kind: "summary",
  });
}

export function saveRecord(
  workspace: RecordWorkspace,
  input: RecordInput,
  existing?: WorkspaceRecord,
) {
  if (existing) {
    if (existing.workspace !== workspace) {
      throw new Error("Record workspace mismatch.");
    }

    return request<WorkspaceRecord>({
      kind: "update",
      workspace,
      id: existing.id,
      revision: existing.revision,
      input,
    });
  }

  return request<WorkspaceRecord>({
    kind: "create",
    workspace,
    input,
  });
}

export function removeRecord(
  record: WorkspaceRecord,
) {
  return request<{ deleted: boolean }>({
    kind: "delete",
    workspace: record.workspace,
    id: record.id,
    revision: record.revision,
  });
}
