"use client";

import {
  useEffect,
  useState,
} from "react";

import {
  navigation,
  type Workspace,
} from "@/lib/navigation";

import {
  WORKSPACE_CONFIG,
  getWorkspaceCounts,
  type RecordWorkspace,
  type WorkspaceSummaryData,
} from "@/lib/workspaces";

import "./FunctionalWorkspace.css";
import "./WorkspaceExperience.css";

export default function WorkspaceSummary({
  onNavigate,
}: {
  onNavigate: (workspace: Workspace) => void;
}) {
  const [summary, setSummary] =
    useState<WorkspaceSummaryData | null>(null);

  const counts = summary?.counts;

  const [failed, setFailed] =
    useState(false);

  useEffect(() => {

    let active = true;

    getWorkspaceCounts()
      .then(result => {
        if (active) setSummary(result);
      })
      .catch(() => {
        if (active) setFailed(true);
      });

    return () => {
      active = false;
    };
  }, []);

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Workspace records</h2>
      </div>

      {summary && (
        <div className="wx-overview-priorities">
          <button onClick={() => onNavigate("tasks")}>
            <span>Open tasks</span>
            <strong>
              {(summary.statuses.tasks.todo ?? 0) +
                (summary.statuses.tasks.in_progress ?? 0)}
            </strong>
          </button>

          <button onClick={() => onNavigate("jobs")}>
            <span>Interviews</span>
            <strong>{summary.statuses.jobs.interview ?? 0}</strong>
          </button>

          <button onClick={() => onNavigate("approvals")}>
            <span>Pending decisions</span>
            <strong>{summary.statuses.approvals.pending ?? 0}</strong>
          </button>

          <button onClick={() => onNavigate("calendar")}>
            <span>Planned events</span>
            <strong>{summary.statuses.calendar.planned ?? 0}</strong>
          </button>
        </div>
      )}

      <div className="fw-summary-grid">
        {Object.keys(WORKSPACE_CONFIG).map(key => {
          const workspace =
            key as RecordWorkspace;

          const label = navigation.find(
            entry => entry.id === workspace,
          )?.label;

          return (
            <button
              key={workspace}
              onClick={() => onNavigate(workspace)}
            >
              <span>{label}</span>

              <strong>
                {counts?.[workspace] ?? "—"}
              </strong>
            </button>
          );
        })}
      </div>

      {!counts && (
        <p className="muted">
          {failed
            ? "Workspace counts unavailable."
            : "Loading workspace record counts..."}
        </p>
      )}

    </section>
  );
}
