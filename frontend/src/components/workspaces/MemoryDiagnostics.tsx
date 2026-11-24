"use client";

import { useEffect, useState } from "react";

import {
  getWorkspaceCounts,
  type WorkspaceSummaryData,
} from "@/lib/workspaces";

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes < 0) return "Unavailable";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KiB";
  return (bytes / 1048576).toFixed(2) + " MiB";
}

export default function MemoryDiagnostics({
  guest,
  refreshKey,
}: {
  guest: boolean;
  refreshKey: number;
}) {
  const [result, setResult] = useState<WorkspaceSummaryData | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (guest) return;

    let active = true;

    getWorkspaceCounts()
      .then(data => {
        if (!active) return;
        setResult(data);
        setFailed(false);
      })
      .catch(() => {
        if (!active) return;
        setResult(null);
        setFailed(true);
      });

    return () => {
      active = false;
    };
  }, [guest, refreshKey]);

  if (guest) {
    return (
      <section className="panel">
        <strong>Private storage diagnostics</strong>
        <p className="muted">
          Available only in Owner mode. No private storage is
          queried in the Guest preview.
        </p>
      </section>
    );
  }

  return (
    <section className="panel wx-diagnostics">
      <h2>Local memory and storage</h2>

      {!result ? (
        <p className="muted">
          {failed
            ? "Diagnostics unavailable. Refresh to retry."
            : "Loading local storage metrics…"}
        </p>
      ) : (
        <div className="wx-metrics">
          <div className="wx-diagnostic">
            <span>Total saved memories</span>
            <strong>{result.counts.memory}</strong>
          </div>

          <div className="wx-diagnostic">
            <span>Saved conversations</span>
            <strong>{result.storage.conversation_count}</strong>
          </div>

          <div className="wx-diagnostic">
            <span>Memory payload storage</span>
            <strong>
              {formatBytes(result.storage.memory_payload_bytes)}
            </strong>
          </div>

          <div className="wx-diagnostic">
            <span>SQLite database pages</span>
            <strong>
              {formatBytes(result.storage.database_page_bytes)}
            </strong>
          </div>
        </div>
      )}

      <p className="muted">
        Database pages measure allocated SQLite storage, including
        unused pages. Backups, temporary files and Docker storage
        are excluded. These figures are not RAM usage or AI
        context limits.
      </p>
    </section>
  );
}
