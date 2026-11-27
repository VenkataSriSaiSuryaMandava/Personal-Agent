"use client";

import {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  Activity,
  Play,
  RefreshCw,
  Workflow,
} from "lucide-react";

import {
  cancelWorkflow,
  createWorkflow,
  executeWorkflow,
  getWorkflow,
  getWorkflowEvents,
  listWorkflows,
  listWorkflowTargets,
  type WorkflowDetail,
  type WorkflowEvent,
  type WorkflowRun,
  type WorkflowTarget,
  type WorkflowType,
} from "@/lib/workflows";

import "./AgentWorkflows.css";

const LABELS: Record<WorkflowType, string> = {
  company_summary: "Company intelligence",
  match_listing: "Job compatibility",
};

function errorMessage(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Workflow operation failed.";
}

function formatTime(value: number) {
  return new Date(value * 1000).toLocaleString();
}

export default function AgentWorkflows({
  guest,
}: {
  guest: boolean;
}) {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [detail, setDetail] =
    useState<WorkflowDetail | null>(null);

  const [events, setEvents] =
    useState<WorkflowEvent[]>([]);

  const [type, setType] =
    useState<WorkflowType>("company_summary");

  const [targets, setTargets] =
    useState<WorkflowTarget[]>([]);

  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [targetLoading, setTargetLoading] =
    useState(true);

  const [error, setError] = useState("");
  const [listFailed, setListFailed] = useState(false);
  const [targetError, setTargetError] =
    useState("");

  const mounted = useRef(false);
  const operation = useRef(false);

  const requestKey = useRef<{
    type: WorkflowType;
    target: string;
    key: string;
  } | null>(null);

  useEffect(() => {
    let active = true;
    mounted.current = true;

    listWorkflows()
      .then(result => {
        if (active) setRuns(result.records);
      })
      .catch(error => {
        if (active) {
          setListFailed(true);
          setError(errorMessage(error));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    const timer = window.setTimeout(() => {
      void listWorkflowTargets(type)
      .then(result => {
        if (!active) return;

        setTargets(result);
        setTarget(result[0]?.id ?? "");
      })
      .catch(error => {
        if (active) {
          setTargetError(errorMessage(error));
        }
      })
      .finally(() => {
        if (active) setTargetLoading(false);
      });

    }, 800);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [type]);

  async function refresh() {
    try {
      const result = await listWorkflows();

      if (mounted.current) {
        setRuns(result.records);
        setListFailed(false);
      }
    } catch (failure) {
      if (mounted.current) setListFailed(true);
      throw failure;
    }
  }

  async function inspect(id: string) {
    const record = await getWorkflow(id);
    const history = await getWorkflowEvents(id);

    if (mounted.current) {
      setDetail(record);
      setEvents(history.events);
    }
  }

  async function perform(action: () => Promise<void>) {
    if (operation.current) return;

    operation.current = true;
    setBusy(true);
    setError("");

    try {
      await action();
    } catch (failure) {
      if (mounted.current) {
        setError(errorMessage(failure));
      }
    } finally {
      operation.current = false;

      if (mounted.current) setBusy(false);
    }
  }

  async function create() {
    if (!target) return;

    if (
      !requestKey.current ||
      requestKey.current.type !== type ||
      requestKey.current.target !== target
    ) {
      requestKey.current = {
        type,
        target,
        key: crypto.randomUUID(),
      };
    }

    const created = await createWorkflow(
      type,
      target,
      requestKey.current.key,
    );

    requestKey.current = null;

    await refresh();
    await inspect(created.id);
  }

  async function reload() {
    await refresh();

    setTargetLoading(true);
    setTargetError("");

    try {
      const result = await listWorkflowTargets(type);

      if (mounted.current) {
        setTargets(result);

        setTarget(current =>
          result.some(row => row.id === current)
            ? current
            : result[0]?.id ?? ""
        );
      }
    } catch (failure) {
      if (mounted.current) {
        setTargetError(errorMessage(failure));
        setTargets([]);
        setTarget("");
      }
    } finally {
      if (mounted.current) {
        setTargetLoading(false);
      }
    }

    if (detail) {
      await inspect(detail.id);
    }
  }

  return (
    <section className="panel aegis-workflows">
      <header className="aw-header">
        <div>
          <span className="eyebrow">AGENT DIAGNOSTICS</span>
          <h2><Workflow size={20}/> Workflows</h2>
          <p className="muted">
            Inspect and manually test registered local capabilities.
          </p>
        </div>

        <button
          type="button"
          className="secondary-button"
          disabled={busy || loading}
          onClick={() => void perform(reload)}
        >
          <RefreshCw size={15}/> Refresh
        </button>
      </header>

      <p className="aw-notice">
        {guest
          ? "Temporary isolated workflows. AI and external actions are disabled."
          : "Local operations only. Scheduled execution is not yet enabled."}
      </p>

      {error && <p role="alert">{error}</p>}

      <form onSubmit={event => {
        event.preventDefault();
        void perform(create);
      }}>
        <fieldset
          disabled={busy || loading}
          className="aw-form"
        >
          <label>
            Operation
            <select
              value={type}
              onChange={event => {
                setTargetLoading(true);
                setTargetError("");
                setTargets([]);
                setTarget("");
                setType(
                  event.target.value as WorkflowType
                );
              }}
            >
              <option value="match_listing">
                Analyze job compatibility
              </option>
              <option value="company_summary">
                Summarize cached company listings
              </option>
            </select>
          </label>

          <label>
            Target
            <select
              value={target}
              disabled={targetLoading}
              onChange={event =>
                setTarget(event.target.value)}
            >
              {!targets.length && (
                <option value="">
                  {targetLoading
                    ? "Loading targets..."
                    : targetError
                      ? "Unable to load targets"
                      : "No targets available"}
                </option>
              )}
              {targets.map(row => (
                <option key={row.id} value={row.id}>
                  {row.label}
                </option>
              ))}
            </select>
          </label>

          <button
            type="submit"
            className="secondary-button"
            disabled={!target || targetLoading}
          >
            Create workflow
          </button>
        </fieldset>
      </form>

      {targetError && (
        <p role="alert">{targetError}</p>
      )}

      {!targetLoading && !targetError && !targets.length && (
        <p className="muted">
          Configure job sources and refresh listings
          in the Career workspace first.
        </p>
      )}

      <div className="aw-layout">
        <div className="aw-list">
          <h3>Recent workflows</h3>

          {loading ? (
            <p role="status">Loading workflows...</p>
          ) : listFailed ? (
            <p role="alert">
              Unable to load workflows. Select Refresh to retry.
            </p>
          ) : runs.length === 0 ? (
            <p className="muted">No workflows yet.</p>
          ) : (
            runs.map(run => (
              <button
                type="button"
                key={run.id}
                className="aw-run"
                disabled={busy}
                aria-pressed={detail?.id === run.id}
                onClick={() => void perform(
                  () => inspect(run.id),
                )}
              >
                <strong>
                  {LABELS[run.workflow_type] ??
                    run.workflow_type}
                </strong>
                <span>{run.status.replaceAll("_", " ")}</span>
                <small>{formatTime(run.created_at)}</small>
              </button>
            ))
          )}
        </div>

        <div className="aw-detail">
          {!detail ? (
            <p className="muted">
              Select a workflow to inspect its state,
              results and activity.
            </p>
          ) : (
            <>
              <h3>
                {LABELS[detail.workflow_type] ??
                  detail.workflow_type}
              </h3>

              <p role="status">
                Status: {detail.status.replaceAll("_", " ")}
              </p>

              <div className="aw-actions">
                {(detail.status === "queued" ||
                  detail.status === "running") && (
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={busy}
                    onClick={() => void perform(
                      async () => {
                        await executeWorkflow(detail.id);
                        await refresh();
                        await inspect(detail.id);
                      },
                    )}
                  >
                    <Play size={15}/>
                    {detail.status === "running"
                      ? "Check or recover"
                      : "Execute locally"}
                  </button>
                )}

                {(detail.status === "queued" ||
                  detail.status === "running") &&
                  !detail.cancellation_requested && (
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={busy}
                      onClick={() => void perform(
                        async () => {
                          await cancelWorkflow(detail);
                          await refresh();
                          await inspect(detail.id);
                        },
                      )}
                    >
                      Cancel
                    </button>
                  )}
              </div>

              {!!detail.cancellation_requested && (
                <p className="muted">
                  Cancellation requested.
                </p>
              )}

              {detail.steps.map(step => (
                <div className="aw-step" key={step.id}>
                  <strong>{step.capability}</strong>
                  <p className="muted">
                    Attempts: {step.attempt_count}
                  </p>

                  {step.error_code && (
                    <p role="alert">
                      {step.error_code.replaceAll("_", " ")}
                    </p>
                  )}

                  {step.output && (
                    <details>
                      <summary>Inspect stored result</summary>
                      <pre>
                        {JSON.stringify(step.output, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
              ))}

              <h3><Activity size={16}/> Activity</h3>

              <ol className="aw-events">
                {events.map(event => (
                  <li key={event.id}>
                    <span>
                      {event.event_type
                        .replace("workflow.", "")
                        .replaceAll("_", " ")}
                    </span>
                    <small>
                      {formatTime(event.created_at)}
                    </small>
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
