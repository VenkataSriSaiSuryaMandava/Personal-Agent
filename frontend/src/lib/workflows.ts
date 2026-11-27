import { workspaceFetch } from "./session-client";

export type WorkflowType =
  | "company_summary"
  | "match_listing";

export type WorkflowStatus =
  | "queued"
  | "running"
  | "waiting_approval"
  | "executing"
  | "completed"
  | "failed"
  | "cancelled"
  | "uncertain";

export interface WorkflowRun {
  id: string;
  workflow_type: WorkflowType;
  target_id: string;
  status: WorkflowStatus;
  revision: number;
  cancellation_requested: number;
  created_at: number;
  updated_at: number;
}

export interface WorkflowStep {
  id: string;
  capability: string;
  status: WorkflowStatus;
  attempt_count: number;
  error_code: string | null;
  output: Record<string, unknown> | null;
}

export interface WorkflowDetail extends WorkflowRun {
  steps: WorkflowStep[];
}

export interface WorkflowEvent {
  id: number;
  event_type: string;
  created_at: number;
}

export interface WorkflowTarget {
  id: string;
  label: string;
}

const BASE = "/api/agent/workflows";

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

function validId(id: string) {
  if (!UUID.test(id)) {
    throw new Error("Invalid workflow identifier.");
  }

  return id;
}

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const method = options?.method ?? "GET";

  const send = () => workspaceFetch(path, {
    ...options,
    cache: "no-store",
    signal: AbortSignal.timeout(35000),
  });

  let response = await send();

  // Retry only reads rejected by admission controls.
  // Never automatically replay a mutation.
  if (method === "GET") {
    for (
      let attempt = 0;
      response.status === 429 && attempt < 2;
      attempt++
    ) {
      await response.body?.cancel().catch(
        () => undefined,
      );

      await new Promise<void>(resolve => {
        setTimeout(resolve, 5000 * (attempt + 1));
      });

      response = await send();
    }
  }

  if (!response.ok) {
    const body = await response.json().catch(
      () => null,
    );

    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : "Workflow operation unavailable.",
    );
  }

  return response.json() as Promise<T>;
}

export function listWorkflows() {
  return request<{
    records: WorkflowRun[];
    next_offset: number | null;
  }>(BASE + "?limit=50");
}

export function getWorkflow(id: string) {
  return request<WorkflowDetail>(
    BASE + "/" + validId(id),
  );
}

export function getWorkflowEvents(id: string) {
  return request<{
    events: WorkflowEvent[];
    next_cursor: number;
    has_more: boolean;
  }>(
    BASE + "/" + validId(id) + "/events",
  );
}

export function createWorkflow(
  workflowType: WorkflowType,
  targetId: string,
  requestKey: string,
) {
  return request<WorkflowRun>(BASE, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      workflow_type: workflowType,
      target_id: validId(targetId),
      request_key: validId(requestKey),
    }),
  });
}

export function executeWorkflow(id: string) {
  return request<WorkflowDetail>(
    BASE + "/" + validId(id) + "/execute",
    { method: "POST" },
  );
}

export function cancelWorkflow(run: WorkflowRun) {
  return request<WorkflowRun>(
    BASE + "/" + validId(run.id) + "/cancel",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        expected_revision: run.revision,
      }),
    },
  );
}

export async function listWorkflowTargets(
  type: WorkflowType,
): Promise<WorkflowTarget[]> {
  if (type === "company_summary") {
    const result = await request<{
      sources: {
        id: string;
        company: string;
        enabled: boolean | number;
      }[];
    }>("/api/agent/career/sources");

    return result.sources
      .filter(row => Boolean(row.enabled))
      .map(row => ({
        id: validId(row.id),
        label: row.company,
      }));
  }

  const result = await request<{
    records?: {
      id: string;
      title: string;
      company: string;
    }[];
    jobs?: {
      id: string;
      title: string;
      company: string;
    }[];
  }>("/api/agent/career/jobs?limit=100");

  const rows = result.jobs ?? result.records;

  if (!Array.isArray(rows)) {
    throw new Error("Job targets unavailable.");
  }

  return rows.map(row => ({
    id: validId(row.id),
    label: [row.title, row.company]
      .filter(Boolean).join(" · "),
  }));
}
