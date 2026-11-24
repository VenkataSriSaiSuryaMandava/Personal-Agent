"use client";

import {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  navigation,
} from "@/lib/navigation";

import {
  WORKSPACE_CONFIG,
  listRecords,
  saveRecord,
  removeRecord,
  type RecordInput,
  type RecordWorkspace,
  type WorkspaceRecord,
} from "@/lib/workspaces";

import { EXPERIENCE } from "@/lib/workspace-experience";
import CalendarBoard from "./CalendarBoard";
import IntegrationPanel from "./IntegrationPanel";
import WorkspaceInsights from "./WorkspaceInsights";
import WorkspaceCollection from "./WorkspaceCollection";
import MemoryDiagnostics from "./MemoryDiagnostics";

import "./FunctionalWorkspace.css";
import "./WorkspaceExperience.css";

function currentTimestamp() {
  return Math.floor(Date.now() / 1000);
}

function currentLocalDay() {
  return localDate(
    new Date().toISOString(),
  ).slice(0, 10);
}

function initialInput(
  workspace: RecordWorkspace,
): RecordInput {
  return {
    title: "",
    detail: "",
    notes: "",
    reference: "",
    scheduled_at: "",
    priority: "normal",
    status: WORKSPACE_CONFIG[workspace].statuses[0],
  };
}

function formatStatus(value: string) {
  return value.replaceAll("_", " ");
}

function localDate(value: string) {
  if (!value) return "";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "";
  }

  const local = new Date(
    date.getTime() -
    date.getTimezoneOffset() * 60000,
  );

  return local.toISOString().slice(0, 16);
}

export default function FunctionalWorkspace({
  workspace,
  guest,
  onAssistant,
}: {
  workspace: RecordWorkspace;
  guest: boolean;
  onAssistant: () => void;
}) {
  const config = WORKSPACE_CONFIG[workspace];
  const experience = EXPERIENCE[workspace];

  const item = navigation.find(
    entry => entry.id === workspace,
  )!;

  const [records, setRecords] =
    useState<WorkspaceRecord[]>([]);

  const [draft, setDraft] = useState(
    () => initialInput(workspace),
  );

  const [editing, setEditing] =
    useState<WorkspaceRecord | null>(null);

  const [showForm, setShowForm] =
    useState(false);

  const [nextOffset, setNextOffset] =
    useState<number | null>(null);

  const [query, setQuery] = useState("");
  const [selectedDate, setSelectedDate] = useState("");
  const [deadline, setDeadline] = useState("all");
  const [metricsRevision, setMetricsRevision] = useState(0);

  const [today, setToday] = useState(currentLocalDay);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setToday(currentLocalDay());
    }, 30000);

    return () => window.clearInterval(timer);
  }, []);
  const [filter, setFilter] = useState("all");
  const [busy, setBusy] = useState(!guest);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const mounted = useRef(false);
  const operation = useRef(false);

  useEffect(() => {
    let active = true;

    mounted.current = true;

    if (!guest) {
      listRecords(workspace)
        .then(result => {
          if (!active) return;

          setRecords(result.records);
          setNextOffset(result.next_offset);
        })
        .catch(() => {
          if (active) {
            setError("Unable to load workspace. Use Refresh to retry.");
          }
        })
        .finally(() => {
          if (active) setBusy(false);
        });
    }

    return () => {
      active = false;
      mounted.current = false;
    };
  }, [workspace, guest]);

  async function reconcileAfterMutation() {
    if (guest || !mounted.current) return;

    // A mutation can change list ordering and offsets.
    // Never continue pagination using the old offset.
    setNextOffset(null);
    setMetricsRevision(value => value + 1);

    try {
      const result = await listRecords(workspace, 0);

      if (!mounted.current) return;

      setRecords(result.records);
      setNextOffset(result.next_offset);
    } catch {
      if (mounted.current) {
        setError(
          "Change saved. Refresh to reload the current list.",
        );
      }
    }
  }

  function change<K extends keyof RecordInput>(
    key: K,
    value: RecordInput[K],
  ) {
    setDraft(previous => ({
      ...previous,
      [key]: value,
    }));
  }

  function newRecord() {
    setEditing(null);
    setDraft(initialInput(workspace));
    setError("");
    setNotice("");
    setShowForm(true);
  }

  function edit(record: WorkspaceRecord) {
    setEditing(record);

    setDraft({
      title: record.title,
      detail: record.detail,
      notes: record.notes,
      reference: record.reference,
      status: record.status,
      scheduled_at: localDate(
        record.scheduled_at,
      ),
      priority: record.priority,
    });

    setError("");
    setNotice("");
    setShowForm(true);
  }

  async function refresh(append = false) {
    if (guest || operation.current) return;

    operation.current = true;
    setBusy(true);
    setError("");
    setNotice("");

    try {
      const result = await listRecords(
        workspace,
        append ? nextOffset ?? 0 : 0,
      );

      if (!mounted.current) return;

      setRecords(previous =>
        append
          ? [...new Map(
            [...previous, ...result.records]
              .map(record => [
                record.id, record,
              ]),
          ).values()]
          : result.records,
      );

      setNextOffset(result.next_offset);
      setMetricsRevision(value => value + 1);
    } catch (failure) {
      if (mounted.current) {
        setError(
          failure instanceof Error
            ? failure.message
            : "Unable to load records.",
        );
      }
    } finally {
      operation.current = false;

      if (mounted.current) setBusy(false);
    }
  }

  async function submit() {
    if (busy || operation.current) return;

    operation.current = true;
    setBusy(true);
    setError("");
    setNotice("");

    try {
      const input = {
        ...draft,
        scheduled_at: draft.scheduled_at
          ? new Date(
              draft.scheduled_at,
            ).toISOString()
          : "",
      };

      let saved: WorkspaceRecord;

      if (guest) {
        const now = currentTimestamp();

        saved = {
          ...input,
          id: editing?.id ??
            crypto.randomUUID(),
          workspace,
          revision:
            (editing?.revision ?? 0) + 1,
          created_at:
            editing?.created_at ?? now,
          updated_at: now,
        };
      } else {
        saved = await saveRecord(
          workspace,
          input,
          editing ?? undefined,
        );
      }

      if (!mounted.current) return;

      setRecords(previous => [
        saved,
        ...previous.filter(
          record => record.id !== saved.id,
        ),
      ]);

      setShowForm(false);
      setEditing(null);

      setNotice(
        guest
          ? "Temporary sample record saved."
          : "Record saved locally.",
      );

      await reconcileAfterMutation();
    } catch (failure) {
      if (mounted.current) {
        setError(
          failure instanceof Error
            ? failure.message
            : "Unable to save record.",
        );
      }
    } finally {
      operation.current = false;

      if (mounted.current) setBusy(false);
    }
  }

  async function remove(
    record: WorkspaceRecord,
  ) {
    if (busy || operation.current) return;

    if (!window.confirm(
      "Delete this record?",
    )) return;

    operation.current = true;
    setBusy(true);
    setError("");
    setNotice("");

    try {
      if (!guest) {
        await removeRecord(record);
      }

      if (!mounted.current) return;

      setRecords(previous =>
        previous.filter(
          entry => entry.id !== record.id,
        ),
      );

      if (editing?.id === record.id) {
        setEditing(null);
        setShowForm(false);
      }

      setNotice("Record deleted.");

      await reconcileAfterMutation();
    } catch (failure) {
      if (mounted.current) {
        setError(
          failure instanceof Error
            ? failure.message
            : "Unable to delete record.",
        );
      }
    } finally {
      operation.current = false;

      if (mounted.current) setBusy(false);
    }
  }

  async function quickStatus(
    record: WorkspaceRecord,
    status: string,
  ) {
    if (busy || operation.current) return;

    operation.current = true;
    setBusy(true);
    setError("");
    setNotice("");

    try {
      const input: RecordInput = {
        title: record.title,
        detail: record.detail,
        notes: record.notes,
        reference: record.reference,
        scheduled_at: record.scheduled_at,
        priority: record.priority,
        status,
      };

      const saved = guest
        ? {
            ...record,
            ...input,
            revision: record.revision + 1,
            updated_at: currentTimestamp(),
          }
        : await saveRecord(workspace, input, record);

      if (!mounted.current) return;

      setRecords(previous => previous.map(entry =>
        entry.id === saved.id ? saved : entry,
      ));

      if (editing?.id === saved.id) {
        setEditing(null);
        setShowForm(false);
      }

      setNotice("Status updated.");
      await reconcileAfterMutation();
    } catch (failure) {
      if (mounted.current) {
        setError(
          failure instanceof Error
            ? failure.message
            : "Unable to update status.",
        );
      }
    } finally {
      operation.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  const visible = records.filter(record => {
    const matchesStatus =
      filter === "all" ||
      record.status === filter;

    const term = query.trim().toLowerCase();

    const matchesText = [
      record.title,
      record.detail,
      record.notes,
      record.reference,
    ].some(value =>
      value.toLowerCase().includes(term),
    );

    const date = record.scheduled_at
      ? localDate(record.scheduled_at).slice(0, 10)
      : "";

    const matchesDate =
      workspace !== "calendar" ||
      !selectedDate ||
      date === selectedDate;

    const matchesDeadline =
      workspace !== "tasks" ||
      deadline === "all" ||
      (deadline === "today" && date === today) ||
      (deadline === "upcoming" &&
        !!date && date > today &&
        record.status !== "completed") ||
      (deadline === "overdue" &&
        !!date && date < today &&
        record.status !== "completed");

    return matchesStatus &&
      matchesText &&
      matchesDate &&
      matchesDeadline;
  });

  return (
    <div className="fw-workspace wx-workspace" data-kind={workspace}>
      <div className="page-heading">
        <div className="eyebrow">
          {guest
            ? "TEMPORARY DEMO"
            : "PRIVATE WORKSPACE"}
        </div>

        <div className="wx-page-title">
          <item.icon size={30}/>
          <h1>{experience.heading}</h1>
        </div>
        <p>{config.description}</p>
      </div>

      <div className="notice">
        {guest
          ? "Use fictional information only. Sample records are temporary and reset when leaving this workspace."
          : "Records stay in your local database. No external actions or AI requests are triggered."}
      </div>

      <WorkspaceInsights
        workspace={workspace}
        records={records}
        filter={filter}
        onFilter={setFilter}
        incomplete={nextOffset !== null}
        guest={guest}
        onAssistant={onAssistant}
      />



      {workspace === "memory" && (
        <MemoryDiagnostics
          guest={guest}
          refreshKey={metricsRevision}
        />
      )}

      {workspace === "calendar" && (
        <CalendarBoard
          records={records}
          selected={selectedDate}
          onSelect={setSelectedDate}
          incomplete={nextOffset !== null}
          busy={busy}
          onCreate={date => {
            newRecord();
            change("scheduled_at", date + "T09:00");
          }}
        />
      )}

      <section className="panel fw-controls wx-toolbar">
        {workspace !== "calendar" && (
        <button
          className="secondary-button"
          disabled={busy}
          onClick={newRecord}
        >
          + {experience.action}
        </button>
        )}

        {!guest && (
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => void refresh()}
          >
            Refresh
          </button>
        )}

        <input
          aria-label="Search records"
          placeholder={"Search " + experience.collection.toLowerCase() + "..."}
          value={query}
          onChange={event =>
            setQuery(event.target.value)
          }
        />

        <select
          aria-label="Filter records by status"
          value={filter}
          onChange={event =>
            setFilter(event.target.value)
          }
        >
          <option value="all">
            All statuses
          </option>

          {config.statuses.map(status => (
            <option key={status} value={status}>
              {formatStatus(status)}
            </option>
          ))}
        </select>
        {workspace === "tasks" && (
          <select
            aria-label="Filter tasks by deadline"
            value={deadline}
            onChange={event => setDeadline(event.target.value)}
          >
            <option value="all">Any deadline</option>
            <option value="today">Today</option>
            <option value="upcoming">Upcoming</option>
            <option value="overdue">Overdue</option>
          </select>
        )}

        {workspace === "calendar" && selectedDate && (
          <button
            type="button"
            className="secondary-button"
            onClick={() => setSelectedDate("")}
          >
            Show all dates
          </button>
        )}
      </section>

      {error && (
        <p
          className="notice error-notice"
          role="alert"
        >
          {error}
        </p>
      )}

      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}

      {showForm && (
        <form
          className="panel fw-form"
          onSubmit={event => {
            event.preventDefault();
            void submit();
          }}
        >
          <h2>
            {editing
              ? "Edit " + experience.singular
              : experience.action}
          </h2>

          <div className="fw-fields">
            <label>
              {config.title}
              <input
                required
                maxLength={160}
                value={draft.title}
                onChange={event =>
                  change("title", event.target.value)
                }
              />
            </label>

            <label>
              {config.detail}
              <input
                maxLength={500}
                value={draft.detail}
                onChange={event =>
                  change("detail", event.target.value)
                }
              />
            </label>

            <label>
              Status
              <select
                value={draft.status}
                onChange={event =>
                  change("status", event.target.value)
                }
              >
                {config.statuses.map(status => (
                  <option
                    key={status}
                    value={status}
                  >
                    {formatStatus(status)}
                  </option>
                ))}
              </select>
            </label>

            {(experience.priority || editing?.priority !== "normal" && !!editing) && (
            <label>
              Priority
              <select
                value={draft.priority}
                onChange={event => {
                  const value = event.target.value;

                  if (
                    value === "low" ||
                    value === "normal" ||
                    value === "high"
                  ) {
                    change("priority", value);
                  }
                }}
              >
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="high">High</option>
              </select>
            </label>
            )}

            {(experience.dateField || !!draft.scheduled_at) && (
            <label>
              {experience.date}
              <input
                type="datetime-local"
                required={workspace === "calendar"}
                value={draft.scheduled_at}
                onChange={event =>
                  change(
                    "scheduled_at",
                    event.target.value,
                  )
                }
              />
            </label>
            )}

            {(experience.reference || !!draft.reference) && (
            <label>
              {config.reference}
              <input
                maxLength={2000}
                value={draft.reference}
                onChange={event =>
                  change("reference", event.target.value)
                }
              />
            </label>
            )}
          </div>

          <label>
            {experience.notes}
            <textarea
              rows={5}
              maxLength={8000}
              value={draft.notes}
              onChange={event =>
                change("notes", event.target.value)
              }
            />
          </label>

          <div className="fw-actions">
            <button
              className="secondary-button fw-primary"
              type="submit"
              disabled={busy || !draft.title.trim()}
            >
              {busy
                ? "Saving..."
                : "Save " + experience.singular}
            </button>

            <button
              className="secondary-button"
              type="button"
              disabled={busy}
              onClick={() => setShowForm(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      <div className="fw-list-heading">
        <h2>{experience.collection}</h2>
        <span className="muted">
          {visible.length} shown
        </span>
      </div>

      {busy && records.length === 0 && (
        <p role="status">Loading records...</p>
      )}

      {workspace !== "jobs" && !busy && visible.length === 0 && (
        <section className="panel fw-empty">
          <item.icon size={32}/>
          <h3>{records.length ? "No matching results" : experience.empty}</h3>
          <p>{records.length ? "Try another filter." : experience.hint}</p>

          {!records.length && (
            <button
              type="button"
              className="secondary-button"
              onClick={newRecord}
            >
              {experience.action}
            </button>
          )}
        </section>
      )}

      {(workspace === "jobs" || visible.length > 0) && (
      <WorkspaceCollection
        workspace={workspace}
        records={visible}
        renderRecord={record => (
          <article
            className="panel fw-record"
            key={record.id}
          >
            <div className="fw-record-head">
              <div className="wx-record-title">
                {workspace === "tasks" && (
                  <input
                    type="checkbox"
                    aria-label={"Complete " + record.title}
                    checked={record.status === "completed"}
                    disabled={busy}
                    onChange={event => void quickStatus(
                      record,
                      event.target.checked ? "completed" : "todo",
                    )}
                  />
                )}

                <h3 data-complete={
                  workspace === "tasks" &&
                  record.status === "completed"
                }>
                  {record.title}
                </h3>
              </div>
              <span className="fw-status" data-status={record.status}>
                {formatStatus(record.status)}
              </span>
            </div>

            {record.detail && (
              <p className="muted">
                {record.detail}
              </p>
            )}

            {record.notes && (
              <div>
                {["research", "coding", "email", "memory"].includes(workspace) && (
                  <p className="wx-field-caption">{experience.notes}</p>
                )}
                <p className="fw-notes">
                  {record.notes}
                </p>
              </div>
            )}

            {record.reference && (
              <div>
                <p className="wx-field-caption">{config.reference}</p>
                <p className="fw-reference">
                  {record.reference}
                </p>
              </div>
            )}

            {record.scheduled_at && (
              <p className="muted">
                {new Date(
                  record.scheduled_at,
                ).toLocaleString()}
              </p>
            )}

            <div className="fw-actions">
              {experience.priority && (
                <span
                  className="wx-priority"
                  data-priority={record.priority}
                >
                  {record.priority} priority
                </span>
              )}

              {workspace === "jobs" && (
                <select
                  aria-label={"Application stage for " + record.title}
                  value={record.status}
                  disabled={busy}
                  onChange={event => void quickStatus(
                    record,
                    event.target.value,
                  )}
                >
                  {config.statuses.map(status => (
                    <option key={status} value={status}>
                      {formatStatus(status)}
                    </option>
                  ))}
                </select>
              )}

              {workspace === "approvals" &&
                record.status === "pending" && (
                <>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={busy}
                    onClick={() => void quickStatus(record, "approved")}
                  >
                    Record approval
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={busy}
                    onClick={() => void quickStatus(record, "rejected")}
                  >
                    Record rejection
                  </button>
                </>
              )}

              <button
                className="secondary-button"
                disabled={busy}
                onClick={() => edit(record)}
              >
                Edit
              </button>

              <button
                className="secondary-button fw-delete"
                disabled={busy}
                onClick={() => void remove(record)}
              >
                {workspace === "memory" ? "Forget" : "Delete"}
              </button>
            </div>
          </article>
        )}
      />

      )}

      <IntegrationPanel
        workspace={workspace}
        guest={guest}
      />

      {!guest && nextOffset !== null && (
        <button
          className="secondary-button"
          disabled={busy}
          onClick={() => void refresh(true)}
        >
          Load more records
        </button>
      )}
    </div>
  );
}
