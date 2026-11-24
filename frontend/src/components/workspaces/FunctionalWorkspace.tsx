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

import "./FunctionalWorkspace.css";

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
}: {
  workspace: RecordWorkspace;
  guest: boolean;
}) {
  const config = WORKSPACE_CONFIG[workspace];

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
        const now = Math.floor(
          Date.now() / 1000,
        );

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

    return matchesStatus && matchesText;
  });

  return (
    <div className="fw-workspace">
      <div className="page-heading">
        <div className="eyebrow">
          {guest
            ? "TEMPORARY DEMO"
            : "PRIVATE WORKSPACE"}
        </div>

        <h1>{item.label}</h1>
        <p>{config.description}</p>
      </div>

      <div className="notice">
        {guest
          ? "Use fictional information only. Sample records are temporary and reset when leaving this workspace."
          : "Records stay in your local database. No external actions or AI requests are triggered."}
      </div>

      <section className="panel fw-controls">
        <button
          className="secondary-button"
          disabled={busy}
          onClick={newRecord}
        >
          + New record
        </button>

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
          placeholder="Search displayed records..."
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
              ? "Edit record"
              : "Create record"}
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

            <label>
              {workspace === "calendar"
                ? "Event date and time"
                : "Date and time (optional)"}
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
          </div>

          <label>
            {workspace === "email"
              ? "Draft message"
              : "Notes"}
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
              {busy ? "Saving..." : "Save record"}
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
        <h2>Records</h2>
        <span className="muted">
          {visible.length} shown
        </span>
      </div>

      {busy && records.length === 0 && (
        <p role="status">Loading records...</p>
      )}

      {!busy && visible.length === 0 && (
        <section className="panel fw-empty">
          <h3>No matching records</h3>
          <p>Create a record or change your filters.</p>
        </section>
      )}

      <div className="fw-records">
        {visible.map(record => (
          <article
            className="panel fw-record"
            key={record.id}
          >
            <div className="fw-record-head">
              <h3>{record.title}</h3>
              <span className="fw-status">
                {formatStatus(record.status)}
              </span>
            </div>

            {record.detail && (
              <p className="muted">
                {record.detail}
              </p>
            )}

            {record.notes && (
              <p className="fw-notes">
                {record.notes}
              </p>
            )}

            {record.reference && (
              <p className="fw-reference">
                {record.reference}
              </p>
            )}

            {record.scheduled_at && (
              <p className="muted">
                {new Date(
                  record.scheduled_at,
                ).toLocaleString()}
              </p>
            )}

            <div className="fw-actions">
              <span className="muted">
                {record.priority} priority
              </span>

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
                Delete
              </button>
            </div>
          </article>
        ))}
      </div>

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
