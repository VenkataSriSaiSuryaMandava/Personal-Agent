"use client";

import {
  CalendarDays,
  Code2,
  Globe,
  LockKeyhole,
  Mail,
} from "lucide-react";

import type { RecordWorkspace } from "@/lib/workspaces";

const CONNECTIONS = {
  email: [
    { name: "Gmail", icon: Mail },
    { name: "Microsoft Outlook", icon: Mail },
  ],
  calendar: [
    { name: "Google Calendar", icon: CalendarDays },
    { name: "Microsoft Outlook Calendar", icon: CalendarDays },
  ],
  coding: [
    { name: "GitHub", icon: Code2 },
    { name: "Local development environment", icon: LockKeyhole },
  ],
  browser: [
    { name: "Browser automation", icon: Globe },
  ],
} as const;

export default function IntegrationPanel({
  workspace,
}: {
  workspace?: RecordWorkspace;
}) {
  const groups = workspace
    ? Object.entries(CONNECTIONS).filter(
        ([key]) => key === workspace,
      )
    : Object.entries(CONNECTIONS);

  if (!groups.length) return null;

  return (
    <section className="panel wx-integrations">
      <div className="wx-section-heading">
        <div>
          <h2>Connections</h2>
          <p className="muted">
            External account access is not enabled.
          </p>
        </div>
        <LockKeyhole size={20} />
      </div>

      <div className="wx-integration-grid">
        {groups.flatMap(([key, providers]) =>
          providers.map(provider => (
            <article
              className="wx-integration"
              key={key + provider.name}
            >
              <provider.icon size={22} />

              <div>
                <strong>{provider.name}</strong>
                <p className="muted">Not connected</p>
              </div>

              <button
                className="secondary-button"
                type="button"
                disabled
                title="Integration is not yet available"
              >
                {key === "calendar"
                  ? "Sync unavailable"
                  : "Not available"}
              </button>
            </article>
          )),
        )}
      </div>

      <p className="muted">
        Future integrations require explicit authorization. No credentials are collected here.
      </p>
    </section>
  );
}
