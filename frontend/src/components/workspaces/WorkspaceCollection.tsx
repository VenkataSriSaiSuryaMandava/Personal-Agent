"use client";

import { useState, type ReactNode } from "react";

import type {
  RecordWorkspace,
  WorkspaceRecord,
} from "@/lib/workspaces";

const JOB_STAGES = [
  "saved",
  "applied",
  "interview",
  "offer",
  "rejected",
  "withdrawn",
];

export default function WorkspaceCollection({
  workspace,
  records,
  renderRecord,
}: {
  workspace: RecordWorkspace;
  records: WorkspaceRecord[];
  renderRecord: (record: WorkspaceRecord) => ReactNode;
}) {
  const [selected, setSelected] = useState("");

  if (workspace === "jobs") {
    return (
      <section className="wx-pipeline" aria-label="Application pipeline">
        {JOB_STAGES.map(stage => {
          const group = records.filter(
            record => record.status === stage,
          );

          return (
            <section className="wx-pipeline-column" key={stage}>
              <div className="wx-column-heading">
                <strong>{stage}</strong>
                <span>{group.length}</span>
              </div>

              {group.length
                ? group.map(renderRecord)
                : <p className="wx-stage-empty">No applications</p>}
            </section>
          );
        })}
      </section>
    );
  }

  if (workspace === "email") {
    const current = records.find(
      record => record.id === selected,
    ) ?? records[0];

    return (
      <section className="wx-email-layout">
        <div className="panel wx-email-list">
          <h2>Drafts and archived messages</h2>

          {records.map(record => (
            <button
              type="button"
              key={record.id}
              aria-pressed={current?.id === record.id}
              data-selected={current?.id === record.id}
              onClick={() => setSelected(record.id)}
            >
              <strong>{record.title}</strong>
              <span>{record.detail || "No recipient"}</span>
              <small>{record.status}</small>
            </button>
          ))}
        </div>

        <div className="wx-email-preview">
          {current && renderRecord(current)}
        </div>
      </section>
    );
  }

  if (workspace === "approvals") {
    const pending = records.filter(
      record => record.status === "pending",
    );

    const history = records.filter(
      record => record.status !== "pending",
    );

    return (
      <div className="wx-decision-layout">
        <section>
          <h2>Pending decisions · {pending.length}</h2>

          {pending.length
            ? pending.map(renderRecord)
            : <p className="panel muted">No pending decisions.</p>}
        </section>

        <section>
          <h2>Decision history · {history.length}</h2>

          {history.length
            ? history.map(renderRecord)
            : <p className="panel muted">No recorded decisions.</p>}
        </section>
      </div>
    );
  }

  return (
    <div
      className="fw-records"
      data-layout={
        ["tasks", "calendar", "browser"].includes(workspace)
          ? "list"
          : "cards"
      }
    >
      {records.map(renderRecord)}
    </div>
  );
}
