"use client";

import type { Workspace } from "@/lib/navigation";
import { navigation } from "@/lib/navigation";
import "./WorkspacePreview.css";

type PreviewWorkspace = Exclude<
  Workspace,
  "overview" | "chat" | "settings"
>;

type Preview = {
  subtitle: string;
  current: string;
  planned: readonly string[];
  example?: string;
  action?: "chat" | "settings";
};

const CONTENT: Record<PreviewWorkspace, Preview> = {
  tasks: {
    subtitle: "Organize work and track what comes next.",
    current: "Task automation and saved task lists are not connected.",
    planned: [
      "Create and prioritize tasks",
      "Track progress and deadlines",
      "Request approval before automated actions",
    ],
    example: "Help me break a fictional project into weekly milestones.",
    action: "chat",
  },
  jobs: {
    subtitle: "A dedicated workspace for your job search.",
    current: "Job tracking and live job discovery are not connected.",
    planned: [
      "Track applications and interview stages",
      "Compare job descriptions against a resume",
      "Organize follow-ups and opportunities",
    ],
    example: "Help me build a sample job application tracking strategy.",
    action: "chat",
  },
  email: {
    subtitle: "Review and prepare messages in one place.",
    current: "No email account is connected.",
    planned: [
      "Review connected messages",
      "Draft replies for approval",
      "Require confirmation before sending",
    ],
  },
  calendar: {
    subtitle: "Plan time without losing control of your schedule.",
    current: "No calendar account is connected.",
    planned: [
      "Review upcoming events",
      "Prepare scheduling suggestions",
      "Confirm changes before writing to a calendar",
    ],
  },
  research: {
    subtitle: "Collect information and develop useful findings.",
    current: "Live web research and source collection are not connected.",
    planned: [
      "Search public sources",
      "Compare findings with citations",
      "Organize research notes",
    ],
    example: "Explain how retrieval-augmented generation works.",
    action: "chat",
  },
  coding: {
    subtitle: "Plan, understand and review code.",
    current: "Repository access and code execution are not connected.",
    planned: [
      "Inspect authorized repositories",
      "Review proposed code changes",
      "Require approval before executing commands",
    ],
    example: "Explain binary search with a Python example.",
    action: "chat",
  },
  browser: {
    subtitle: "Controlled browser workflows.",
    current: "Browser automation is disabled.",
    planned: [
      "Preview browser actions",
      "Use scoped website permissions",
      "Ask before submitting forms or changing data",
    ],
  },
  memory: {
    subtitle: "Manage what your personal agent remembers.",
    current: "Persistent personal-agent memory is not implemented.",
    planned: [
      "Review saved memories",
      "Control retention and deletion",
      "Keep private memory local",
    ],
  },
  approvals: {
    subtitle: "Review permissions before actions happen.",
    current: "No automated tools or action approval queue are enabled.",
    planned: [
      "Review requested tool permissions",
      "Approve or reject sensitive actions",
      "Inspect action history",
    ],
    action: "settings",
  },
};

export default function WorkspacePreview({
  workspace,
  onNavigate,
  onOpenSecurity,
}: {
  workspace: PreviewWorkspace;
  onNavigate: (workspace: Workspace) => void;
  onOpenSecurity: () => void;
}) {
  const content = CONTENT[workspace];
  const item = navigation.find(entry => entry.id === workspace)!;
  const Icon = item.icon;

  return (
    <div className="aw-workspace">
      <div className="page-heading">
        <div className="eyebrow">WORKSPACE</div>
        <h1>{item.label}</h1>
        <p>{content.subtitle}</p>
      </div>

      <div className="aw-heading">
        <div className="aw-symbol">
          <Icon size={24} />
        </div>

        <div>
          <h2>{item.label} workspace</h2>
          <p>Designed for the next stages of Aegis AI.</p>
        </div>

        <span className="aw-badge">
          Planned
        </span>
      </div>

      <div className="aw-grid">
        <section className="panel aw-card">
          <h3>Current availability</h3>
          <p>{content.current}</p>
          <div className="aw-note">
            No external accounts or permissions are
            activated by opening this page.
          </div>
        </section>

        <section className="panel aw-card">
          <h3>Coming next</h3>
          <ul>
            {content.planned.map(feature => (
              <li key={feature}>{feature}</li>
            ))}
          </ul>
        </section>
      </div>

      {(content.example || content.action === "settings") && (
        <section className="panel aw-next">
          <div>
            <h3>
              {content.action === "settings"
                ? "Available security controls"
                : "What you can do now"}
            </h3>

            <p>
              {content.example
                ? "You can already ask the AI Assistant about general, non-private topics."
                : "Review the existing security preferences and emergency stop."}
            </p>

            {content.example && (
              <p className="aw-example">
                Example: {content.example}
              </p>
            )}
          </div>

          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              if (content.action === "settings") {
                onOpenSecurity();
              } else {
                onNavigate("chat");
              }
            }}
          >
            {content.action === "settings"
              ? "Open Security"
              : "Open AI Assistant"}
          </button>
        </section>
      )}
    </div>
  );
}
