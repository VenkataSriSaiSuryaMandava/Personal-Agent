"use client";

import { useState } from "react";

import {
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  Globe,
  ShieldCheck,
} from "lucide-react";

import {
  WORKSPACE_CONFIG,
  type RecordWorkspace,
  type WorkspaceRecord,
} from "@/lib/workspaces";

export default function WorkspaceInsights({
  workspace,
  records,
  filter,
  onFilter,
  incomplete,
  publicMode,
  onAssistant,
}: {
  workspace: RecordWorkspace;
  records: WorkspaceRecord[];
  filter: string;
  onFilter: (value: string) => void;
  incomplete: boolean;
  publicMode: boolean;
  onAssistant: () => void;
}) {
  const [search, setSearch] = useState("");
  const [engine, setEngine] = useState("google");

  const statuses = WORKSPACE_CONFIG[workspace].statuses;

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
      {workspace === "memory" || workspace === "jobs" || workspace === "email" ||
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
              {publicMode ? "Temporary session memory" : "Private local memory"}
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
              disabled={!search.trim()}
            >
              Search externally <ArrowUpRight size={15}/>
            </button>
          </form>

          <p className="muted">
            Search opens your selected external search engine.
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
