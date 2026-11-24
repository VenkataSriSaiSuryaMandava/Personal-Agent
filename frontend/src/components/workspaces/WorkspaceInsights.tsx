"use client";

import { useState } from "react";

import {
  ArrowUpRight,
  Brain,
  CheckCircle2,
  Clock3,
  Database,
  Globe,
  ShieldCheck,
} from "lucide-react";

import {
  WORKSPACE_CONFIG,
  type RecordWorkspace,
  type WorkspaceRecord,
} from "@/lib/workspaces";

function bytesLabel(bytes: number) {
  if (bytes < 1024) return bytes + " B";

  if (bytes < 1024 * 1024) {
    return (bytes / 1024).toFixed(1) + " KiB";
  }

  return (bytes / 1024 / 1024).toFixed(1) + " MiB";
}

export default function WorkspaceInsights({
  workspace,
  records,
  filter,
  onFilter,
  incomplete,
  guest,
  onAssistant,
}: {
  workspace: RecordWorkspace;
  records: WorkspaceRecord[];
  filter: string;
  onFilter: (value: string) => void;
  incomplete: boolean;
  guest: boolean;
  onAssistant: () => void;
}) {
  const [search, setSearch] = useState("");
  const [engine, setEngine] = useState("google");

  const statuses = WORKSPACE_CONFIG[workspace].statuses;

  const contentBytes = records.reduce(
    (total, record) => total +
      new TextEncoder().encode(JSON.stringify({
        title: record.title,
        notes: record.notes,
        detail: record.detail,
        reference: record.reference,
      })).length,
    0,
  );

  function launchSearch() {
    const term = search.trim();

    if (!term) return;

    // A manually initiated external navigation.
    // Never attach workspace records to this request.
    const query = new URLSearchParams({ q: term });

    let destination: URL;

    switch (engine) {
      case "bing":
        destination = new URL("https://www.bing.com/search");
        break;
      case "duckduckgo":
        destination = new URL("https://duckduckgo.com/");
        break;
      default:
        destination = new URL("https://www.google.com/search");
    }

    destination.search = query.toString();

    if (!window.confirm(
      "Send the typed search query to your selected search engine? Do not include private information.",
    )) return;

    window.open(
      destination.toString(),
      "_blank",
      "noopener,noreferrer",
    );
  }

  return (
    <>
      {workspace === "memory" ? (
        guest ? (
        <div className="wx-metrics">
          <article className="panel wx-metric">
            <Brain size={20}/>
            <span>Loaded memories</span>
            <strong>{records.length}</strong>
          </article>

          <article className="panel wx-metric">
            <Database size={20}/>
            <span>Loaded content size</span>
            <strong>{bytesLabel(contentBytes)}</strong>
          </article>

          <article className="panel wx-metric">
            <ShieldCheck size={20}/>
            <span>AI memory access</span>
            <strong>Off</strong>
          </article>
        </div>
        ) : null
      ) : workspace === "jobs" || workspace === "email" ||
          workspace === "calendar" ? null : (
        <div className="wx-metrics">
          {statuses.map(status => (
            <button
              type="button"
              className="panel wx-metric"
              key={status}
              data-active={filter === status}
              aria-pressed={filter === status}
              onClick={() => onFilter(
                filter === status ? "all" : status,
              )}
            >
              {["completed", "approved", "offer"].includes(status)
                ? <CheckCircle2 size={20}/>
                : <Clock3 size={20}/>}

              <span>{status.replaceAll("_", " ")}</span>

              <strong>
                {records.filter(record =>
                  record.status === status,
                ).length}
              </strong>
            </button>
          ))}
        </div>
      )}

      {incomplete && (
        <p className="muted">
          Metrics include loaded records only.
        </p>
      )}

      {workspace === "memory" && (
        <section className="panel wx-info">
          <ShieldCheck size={22}/>

          <div>
            <strong>
              {guest ? "Temporary memory preview" : "Private local memory"}
            </strong>

            <p className="muted">
              Content size measures loaded memory text encoded
              as JSON. It is not total database size, RAM usage
              or model context capacity.
              Saved memories are not automatically sent to AI.
            </p>
          </div>
        </section>
      )}

      {workspace === "approvals" && (
        <section className="panel wx-info">
          <ShieldCheck size={22}/>

          <div>
            <strong>External execution disabled</strong>
            <p className="muted">
              Approval records represent your manual decisions.
              They do not grant access or trigger actions.
            </p>
          </div>
        </section>
      )}

      {workspace === "browser" && (
        <section className="panel wx-search">
          <div className="wx-section-heading">
            <h2>Search the web</h2>
            <Globe size={20}/>
          </div>

          <form
            className="fw-controls"
            onSubmit={event => {
              event.preventDefault();
              launchSearch();
            }}
          >
            <select
              aria-label="Search engine"
              value={engine}
              onChange={event => setEngine(event.target.value)}
            >
              <option value="google">Google</option>
              <option value="bing">Bing</option>
              <option value="duckduckgo">DuckDuckGo</option>
            </select>

            <input
              aria-label="Web search query"
              placeholder="Enter a public search query"
              value={search}
              maxLength={500}
              onChange={event => setSearch(event.target.value)}
            />

            <button
              className="secondary-button fw-primary"
              disabled={!search.trim() || guest}
            >
              Search externally <ArrowUpRight size={15}/>
            </button>
          </form>

          <p className="muted">
            {guest
              ? "External searching is disabled in Guest mode."
              : "Opens your default browser. Only the typed query is shared after confirmation."}
          </p>
        </section>
      )}

      {(workspace === "research" || workspace === "coding") && (
        <section className="panel wx-info">
          <div className="wx-grow">
            <strong>
              {workspace === "research"
                ? "Explore ideas with Aegis"
                : "Get coding assistance"}
            </strong>

            <p className="muted">
              Open the assistant to discuss public or synthetic
              information. Saved records are not attached automatically.
            </p>
          </div>

          <button
            type="button"
            className="secondary-button"
            onClick={onAssistant}
          >
            Open assistant
          </button>
        </section>
      )}
    </>
  );
}
