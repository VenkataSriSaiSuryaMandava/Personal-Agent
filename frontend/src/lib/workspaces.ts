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

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(
    "/api/agent/workspaces/" + path,
    {
      ...options,
      credentials: "same-origin",
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    },
  );

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
  }>(
    workspace + "?limit=100&offset=" + offset,
  );
}

export function getWorkspaceCounts() {
  return request<{
    counts: WorkspaceCounts;
  }>("summary");
}

export function saveRecord(
  workspace: RecordWorkspace,
  input: RecordInput,
  existing?: WorkspaceRecord,
) {
  return request<WorkspaceRecord>(
    workspace +
      (existing ? "/" + existing.id : ""),
    {
      method: existing ? "PATCH" : "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ...input,
        ...(existing ? {
          expected_revision: existing.revision,
        } : {}),
      }),
    },
  );
}

export function removeRecord(
  record: WorkspaceRecord,
) {
  return request<{ deleted: boolean }>(
    record.workspace + "/" + record.id +
      "?revision=" + record.revision,
    { method: "DELETE" },
  );
}
