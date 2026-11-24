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
  type WorkspaceCounts,
} from "@/lib/workspaces";

import "./FunctionalWorkspace.css";

export default function WorkspaceSummary({
  guest,
  onNavigate,
}: {
  guest: boolean;
  onNavigate: (workspace: Workspace) => void;
}) {
  const [counts, setCounts] =
    useState<WorkspaceCounts | null>(null);

  const [failed, setFailed] =
    useState(false);

  useEffect(() => {
    if (guest) return;

    let active = true;

    getWorkspaceCounts()
      .then(result => {
        if (active) setCounts(result.counts);
      })
      .catch(() => {
        if (active) setFailed(true);
      });

    return () => {
      active = false;
    };
  }, [guest]);

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Workspace records</h2>
      </div>

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
                {guest
                  ? "Demo"
                  : counts?.[workspace] ?? "—"}
              </strong>
            </button>
          );
        })}
      </div>

      {!guest && !counts && (
        <p className="muted">
          {failed
            ? "Workspace counts unavailable."
            : "Loading local record counts..."}
        </p>
      )}

      {guest && (
        <p className="muted">
          Guest records are temporary.
        </p>
      )}
    </section>
  );
}
