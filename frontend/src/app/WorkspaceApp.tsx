"use client";

import {
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import { PanelLeft, MessageSquare } from "lucide-react";

import AuthGate from "@/components/auth/AuthGate";
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";
import StatusCard from "@/components/dashboard/StatusCard";
import Conversation from "@/components/dashboard/Conversation";
import SystemStatus from "@/components/dashboard/SystemStatus";
import Approvals from "@/components/dashboard/Approvals";
import SettingsWorkspace from "@/components/settings/SettingsWorkspace";
import FunctionalWorkspace from "@/components/workspaces/FunctionalWorkspace";
import CareerWorkspace from "@/components/workspaces/CareerWorkspace";
import WorkspaceSummary from "@/components/workspaces/WorkspaceSummary";

import {
  readWorkspaceLocation,
  writeWorkspaceLocation,
  type SettingsSection,
} from "@/lib/workspace-location";

import {
  navigation,
  type Workspace,
} from "@/lib/navigation";

import {
  getSettings,
  resetSettings,
  updateSettings,
  type GeneralPreferences,
  type SecurityPreferences,
  type SettingsSnapshot,
} from "@/lib/settings";

function subscribeColorScheme(callback: () => void) {
  const media = window.matchMedia(
    "(prefers-color-scheme: dark)"
  );

  media.addEventListener("change", callback);

  return () => {
    media.removeEventListener("change", callback);
  };
}

function getColorScheme() {
  return window.matchMedia(
    "(prefers-color-scheme: dark)"
  ).matches;
}

function serverColorScheme() {
  return true;
}

export default function WorkspaceApp({
  publicMode,
}: {
  publicMode: boolean;
}) {
  return (
    <AuthGate publicMode={publicMode}>
      {guest => <Dashboard publicMode={publicMode || guest} />}
    </AuthGate>
  );
}

function Dashboard({ publicMode }: { publicMode: boolean }) {
  const [active, setActive] =
    useState<Workspace>("overview");

  const [settingsSection, setSettingsSection] =
    useState<SettingsSection>("general");

  const [snapshot, setSnapshot] =
    useState<SettingsSnapshot | null>(null);

  const [collapsed, setCollapsed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);

  const operation = useRef(false);
  const navigationRevision = useRef(0);

  function clearNavigationNotice() {
    navigationRevision.current += 1;
    setMessage("");
    setFailed(false);
  }

  const systemDark = useSyncExternalStore(
    subscribeColorScheme,
    getColorScheme,
    serverColorScheme
  );

  const theme = snapshot?.settings.theme ?? "dark";

  const dark = theme === "system"
    ? systemDark
    : theme === "dark";

  const current = navigation.find(
    item => item.id === active
  )!;

  useEffect(() => {
    let mounted = true;

    getSettings()
      .then(result => {
        if (!mounted) return;

        setSnapshot(result);

        const location = readWorkspaceLocation(
          result.settings.startup_workspace
        );

        setActive(location.workspace);
        setSettingsSection(location.section);

        writeWorkspaceLocation(
          location.workspace,
          location.section,
          true
        );
      })
      .catch(() => {
        if (!mounted) return;

        const location = readWorkspaceLocation();

        setActive(location.workspace);
        setSettingsSection(location.section);

        setFailed(true);
        setMessage(
          "Saved preferences are unavailable. Reload settings to retry."
        );
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    function restoreLocation() {
      navigationRevision.current += 1;
      setMessage("");
      setFailed(false);

      const location = readWorkspaceLocation(
        snapshot?.settings.startup_workspace ?? "overview"
      );

      setActive(location.workspace);
      setSettingsSection(location.section);
    }

    window.addEventListener(
      "popstate",
      restoreLocation
    );

    return () => {
      window.removeEventListener(
        "popstate",
        restoreLocation
      );
    };
  }, [snapshot?.settings.startup_workspace]);

  function navigate(workspace: Workspace) {
    window.scrollTo({ top: 0, behavior: "instant" });
    clearNavigationNotice();

    const section =
      workspace === "settings" && active === "settings"
        ? settingsSection
        : "general";

    setActive(workspace);
    setSettingsSection(section);

    writeWorkspaceLocation(
      workspace,
      section
    );
  }

  function navigateSettings(section: SettingsSection) {
    window.scrollTo({ top: 0, behavior: "instant" });
    clearNavigationNotice();
    setSettingsSection(section);

    writeWorkspaceLocation(
      "settings",
      section
    );
  }

  async function perform(
    action: () => Promise<SettingsSnapshot>,
    success: string
  ): Promise<boolean> {
    if (operation.current) return false;

    operation.current = true;
    const startedAt = navigationRevision.current;

    setBusy(true);
    setMessage("");

    try {
      const result = await action();

      setSnapshot(result);

      if (startedAt === navigationRevision.current) {
        setFailed(false);
        setMessage(success);
      }

      return true;
    } catch (error) {
      if (startedAt === navigationRevision.current) {
        setFailed(true);

        setMessage(
          error instanceof Error
            ? error.message
            : "Settings operation failed."
        );
      }

      return false;
    } finally {
      operation.current = false;
      setBusy(false);
    }
  }

  async function save(
    changes: Partial<GeneralPreferences & SecurityPreferences>
  ) {
    if (!snapshot) return false;

    return perform(
      () => updateSettings(changes, snapshot.revision),
      "Preferences saved."
    );
  }

  async function reset() {
    if (!snapshot) return false;

    return perform(
      () => resetSettings(snapshot.revision),
      "General preferences restored."
    );
  }

  async function reload() {
    return perform(
      getSettings,
      "Settings reloaded."
    );
  }

  return (
    <div
      className="app-shell ac-shell"
      data-theme={dark ? "dark" : "light"}
      data-sidebar={collapsed ? "collapsed" : "expanded"}
      data-workspace={active}
    >
      <Sidebar active={active} onNavigate={navigate}/>

      <main className="main-content">
        <div className="ac-topbar-wrap">
          <button
            className="icon-button ac-sidebar-toggle"
            aria-label={
              collapsed ? "Expand sidebar" : "Collapse sidebar"
            }
            aria-expanded={!collapsed}
            onClick={() => setCollapsed(!collapsed)}
          >
            <PanelLeft size={19}/>
          </button>

          <Header
            title={current.label}
            dark={dark}
            guest={publicMode}
            themeDisabled={loading || busy || !snapshot}
            onToggleTheme={() => {
              void save({ theme: dark ? "light" : "dark" });
            }}
          />
        </div>

        <div className="workspace-content ac-workspace">
          {message && (
            <div
              className={
                failed
                  ? "as-error as-global-message"
                  : "as-global-message muted"
              }
              role={failed ? "alert" : "status"}
            >
              {message}
              {" "}
              <button
                type="button"
                className="secondary-button"
                onClick={() => setMessage("")}
              >
                Dismiss
              </button>
            </div>
          )}

          {loading ? (
            <section className="panel" role="status">
              Loading workspace preferences…
            </section>
          ) : (
            <>
              <div
                className="ac-chat-workspace"
                hidden={active !== "chat"}
              >
                <Conversation
                  guest={publicMode}
                  retain={!publicMode &&
                    snapshot?.settings.retain_conversations === true}
                />
              </div>

              {active === "overview" && (
                <>
                  <div className="page-heading">
                    <div className="eyebrow">
                      SYSTEM OVERVIEW
                    </div>
                    <h1>Your command center.</h1>
                    <p>
                      View service status, security controls
                      and available features.
                    </p>
                  </div>

                  <div className="stats-grid">
                    <StatusCard
                      title="AI provider"
                      value={publicMode ? "Disabled" : "Gemini"}
                      description={
                        publicMode
                          ? "AI disabled in this deployment"
                          : "Gemini conversational AI"
                      }
                    />
                    <StatusCard
                      title="Task engine"
                      value="Manual"
                      description="Tasks and deadlines"
                    />
                    <StatusCard
                      title="Integrations"
                      value="Offline"
                      description="External accounts not connected"
                    />
                    <StatusCard
                      title="Execution"
                      value="Off"
                      description="Text responses only"
                    />
                  </div>

                  <div className="dashboard-grid">
                    <div className="right-column">
                      <section className="panel ac-overview-card">
                        <MessageSquare size={26}/>
                        <h2>Start a conversation</h2>
                        <p>
                          {publicMode
                            ? "AI is unavailable in the public deployment."
                            : "Ask questions, compare ideas and generate code with the AI assistant."}
                        </p>
                        <button
                          className="secondary-button"
                          onClick={() => navigate("chat")}
                        >
                          {publicMode ? "Open Chat" : "Ask Aegis →"}
                        </button>
                      </section>



                      <section className="panel ac-overview-card">
                        <h2>Control your workspace</h2>
                        <p>
                          Configure preferences, inspect providers
                          and review settings activity.
                        </p>
                        <button
                          className="secondary-button"
                          onClick={() => navigate("settings")}
                        >
                          Open Settings →
                        </button>
                      </section>
                    </div>

                    <div className="right-column">
                      <WorkspaceSummary

                        onNavigate={navigate}
                      />
                      <SystemStatus />
                      <Approvals
                        onOpen={() => navigate("approvals")}
                      />
                    </div>
                  </div>
                </>
              )}

              {active === "settings" && (
                snapshot ? (
                  <SettingsWorkspace
                    publicMode={publicMode}
                    section={settingsSection}
                    onSectionChange={navigateSettings}
                    snapshot={snapshot}
                    busy={busy}
                    onSave={save}
                    onReset={reset}
                    onReload={reload}
                  />
                ) : (
                  <section className="panel as-panel">
                    <h2>Settings unavailable</h2>
                    <p>
                      Saved preferences could not be loaded.
                    </p>
                    <button
                      className="secondary-button"
                      disabled={busy}
                      onClick={() => void reload()}
                    >
                      Reload settings
                    </button>
                  </section>
                )
              )}

              {active === "jobs" && (
                <CareerWorkspace
                  publicMode={publicMode}
                  onAssistant={() => navigate("chat")}
                />
              )}

              {active !== "chat" &&
               active !== "overview" &&
               active !== "settings" &&
               active !== "jobs" && (
                <FunctionalWorkspace
                  key={active}
                  workspace={active}
                  publicMode={publicMode}
                  onAssistant={() => navigate("chat")}
                />
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
