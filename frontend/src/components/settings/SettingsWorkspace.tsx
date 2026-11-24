"use client";

import IntegrationPanel from "../workspaces/IntegrationPanel";
import "../workspaces/WorkspaceExperience.css";

import {
  useEffect,
  useState,
  type ReactNode,
} from "react";

import {
  Activity,
  Brain,
  Database,
  Globe,
  Info,
  Lock,
  Monitor,
  Moon,
  RefreshCw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  Sun,
  RotateCcw,
} from "lucide-react";

import {
  getAudit,
  getProviders,
  getStorage,
  type AuditResponse,
  type GeneralPreferences,
  type SecurityPreferences,
  type ProvidersResponse,
  type SettingsSnapshot,
  type StorageResponse,
  type StartupWorkspace,
  type ResponseStyle,
} from "@/lib/settings";

import type {
  SettingsSection,
} from "@/lib/workspace-location";

import "./SettingsWorkspace.css";

const SECTIONS = [
  { id: "general", title: "General", icon: SlidersHorizontal },
  { id: "ai", title: "AI & Models", icon: Brain },
  { id: "integrations", title: "Integrations", icon: Globe },
  { id: "security", title: "Security", icon: ShieldCheck },
  { id: "privacy", title: "Privacy", icon: Lock },
  { id: "storage", title: "Storage", icon: Database },
  { id: "audit", title: "Audit log", icon: Activity },
] as const;

type Props = {
  guest?: boolean;
  section: SettingsSection;
  onSectionChange: (section: SettingsSection) => void;
  snapshot: SettingsSnapshot;
  busy: boolean;
  onSave: (
    changes: Partial<GeneralPreferences & SecurityPreferences>
  ) => Promise<boolean>;
  onReset: () => Promise<boolean>;
  onReload: () => Promise<boolean>;
};

function SettingRow({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <div className="as-row">
      <div>
        <strong>{title}</strong>
        {description && <p>{description}</p>}
      </div>
      <div className="as-row-value">{children}</div>
    </div>
  );
}

function Status({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "good" | "warning";
}) {
  return (
    <span className="as-status" data-tone={tone}>
      {children}
    </span>
  );
}

function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="as-notice">
      <Info size={17} />
      <div>{children}</div>
    </div>
  );
}

function formatTime(seconds: number) {
  return new Date(seconds * 1000).toLocaleString();
}

function GeneralSettings({
  guest,
  snapshot,
  busy,
  onSave,
  onReset,
}: Props) {
  const saved = snapshot.settings;

  const [draft, setDraft] = useState<GeneralPreferences>({
    theme: saved.theme,
    startup_workspace: saved.startup_workspace,
    response_style: saved.response_style,
  });

  const [confirmReset, setConfirmReset] = useState(false);

  const dirty =
    draft.theme !== saved.theme ||
    draft.startup_workspace !== saved.startup_workspace ||
    draft.response_style !== saved.response_style;

  const editable = (field: string) =>
    snapshot.editable_fields.includes(field);

  const appearanceOptions = [
    { value: "dark", label: "Dark", icon: Moon },
    { value: "light", label: "Light", icon: Sun },
    { value: "system", label: "System", icon: Monitor },
  ] as const;

  return (
    <section className="panel as-panel">
      <h2>General preferences</h2>
      <p className="as-description">
        {guest
          ? "Personalize this preview. Changes are temporary."
          : "Personalize your workspace. Changes are stored locally."}
      </p>

      <div className="as-field">
        <strong>Appearance</strong>
        <p>Choose your preferred interface theme.</p>

        <div className="as-theme-grid">
          {appearanceOptions.map(option => (
            <button
              key={option.value}
              type="button"
              disabled={busy || !editable("theme")}
              aria-pressed={draft.theme === option.value}
              className="as-theme-option"
              data-selected={draft.theme === option.value}
              onClick={() => setDraft(previous => ({
                ...previous,
                theme: option.value,
              }))}
            >
              <option.icon size={23} />
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="as-field">
        <label htmlFor="aegis-startup">
          Startup workspace
        </label>
        <p>
          Saved workspace preference.
          Fresh Owner Login always opens Overview.
        </p>

        <select
          id="aegis-startup"
          value={draft.startup_workspace}
          disabled={busy || !editable("startup_workspace")}
          onChange={event => setDraft(previous => ({
            ...previous,
            startup_workspace:
              event.target.value as StartupWorkspace,
          }))}
        >
          <option value="overview">Overview</option>
          <option value="chat">AI Assistant</option>
          <option value="settings">Settings</option>
        </select>
      </div>

      <div className="as-field">
        <label htmlFor="aegis-response-style">
          Response style
        </label>
        <p>
          Saved preference. AI response behavior will be
          connected in a later checkpoint.
        </p>

        <select
          id="aegis-response-style"
          value={draft.response_style}
          disabled={busy || !editable("response_style")}
          onChange={event => setDraft(previous => ({
            ...previous,
            response_style:
              event.target.value as ResponseStyle,
          }))}
        >
          <option value="balanced">Balanced</option>
          <option value="concise">Concise</option>
          <option value="detailed">Detailed</option>
        </select>
      </div>

      {confirmReset && (
        <Notice>
          Reset general preferences to their defaults?
          Security and provider preferences will not change.
        </Notice>
      )}

      <div className="as-actions">
        <span className="as-muted">
          {dirty ? "Unsaved changes" : "All changes saved"}
        </span>

        {confirmReset ? (
          <>
            <button
              className="secondary-button"
              disabled={busy}
              onClick={() => setConfirmReset(false)}
            >
              Cancel
            </button>
            <button
              className="secondary-button"
              disabled={busy}
              onClick={async () => {
                if (await onReset()) {
                  setConfirmReset(false);
                }
              }}
            >
              Confirm reset
            </button>
          </>
        ) : (
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => setConfirmReset(true)}
          >
            <RotateCcw size={15} /> Reset
          </button>
        )}

        <button
          className="as-primary"
          disabled={busy || !dirty}
          onClick={() => {
            const changes: Partial<GeneralPreferences> = {};

            if (draft.theme !== saved.theme) {
              changes.theme = draft.theme;
            }

            if (draft.startup_workspace !==
                saved.startup_workspace) {
              changes.startup_workspace =
                draft.startup_workspace;
            }

            if (draft.response_style !== saved.response_style) {
              changes.response_style = draft.response_style;
            }

            void onSave(changes);
          }}
        >
          <Save size={15} />
          {busy ? "Working…" : "Save changes"}
        </button>
      </div>
    </section>
  );
}

function ProviderSettings({
  providers,
}: {
  providers: ProvidersResponse | null;
}) {
  return (
    <section className="panel as-panel">
      <h2>AI providers</h2>
      <p className="as-description">
        View the authorized AI model and provider configuration.
      </p>

      <Notice>
        Gemini is the only active AI provider. Credentials stay on
        the backend. Configuration status does not verify
        live API availability or remaining quota.
      </Notice>

      {!providers ? (
        <p className="as-muted">
          Provider diagnostics unavailable or loading.
        </p>
      ) : (
        <div className="as-provider-grid">
          {providers.providers.map(provider => (
            <article className="as-provider" key={provider.provider}>
              <div className="as-provider-heading">
                <Brain size={23} />
                <h3>
                  {provider.provider === "gemini" ? "Gemini" : "Groq"}
                </h3>
              </div>

              <Status
                tone={
                  provider.status === "configured"
                  ? "good"
                  : "neutral"
                }
              >
                {provider.status.replaceAll("_", " ")}
              </Status>

              <SettingRow title="Credential configured">
                {provider.configured ? "Yes" : "No"}
              </SettingRow>
              <SettingRow title="Model">
                {provider.model ?? "Not available"}
              </SettingRow>
              <SettingRow title="Live connection verified">
                {provider.live_verified ? "Yes" : "No"}
              </SettingRow>
            </article>
          ))}
        </div>
      )}

      <SettingRow
        title="Automatic fallback"
        description="No automatic transmission to another provider."
      >
        <Status>Disabled</Status>
      </SettingRow>
    </section>
  );
}

type SecurityField =
  "cloud_enabled" | "emergency_stop" | "retain_conversations";

function SecurityControl({
  title,
  description,
  field,
  enabled,
  busy,
  editable,
  enforced,
  onSave,
}: {
  title: string;
  description: string;
  field: SecurityField;
  enabled: boolean;
  busy: boolean;
  editable: boolean;
  enforced: boolean;
  onSave: Props["onSave"];
}) {
  const [confirm, setConfirm] = useState(false);

  const isEmergency = field === "emergency_stop";
  const isRetention = field === "retain_conversations";
  const nextValue = !enabled;

  const available = editable && enforced && !busy;

  const stateLabel = !enforced
    ? "Unavailable"
    : isEmergency
      ? enabled ? "Stop active" : "Stop inactive"
      : enabled ? "Enabled" : "Disabled";

  const confirmationTitle = isEmergency
    ? nextValue ? "Activate emergency stop" : "Deactivate emergency stop"
    : isRetention
      ? nextValue ? "Enable conversation history" : "Disable conversation history"
      : nextValue ? "Enable cloud AI access" : "Disable cloud AI access";

  const warning = isEmergency
    ? nextValue
      ? "Activate emergency stop? New cloud requests will be blocked. Already transmitted requests cannot be recalled."
      : "Deactivate emergency stop? Cloud inference will still require separate authorization and server permission."
    : isRetention
      ? nextValue
        ? "Save future conversations locally? Existing saved history remains until deleted."
        : "Stop saving new conversations? Previously saved history will remain available."
      : nextValue
        ? "Enable cloud AI? Approved public or synthetic content may be transmitted to an external provider. Never include private information."
        : "Disable cloud AI? New external AI requests will be denied.";

  return (
    <div
      className="as-control-card"
      data-enabled={enabled}
      data-emergency={isEmergency}
    >
      <div className="as-control-main">
        <div className="as-control-copy">
          <div className="as-control-heading">
            <h3>{title}</h3>

            <span
              className="as-state-pill"
              data-active={enabled}
              data-emergency={isEmergency}
            >
              <span className="as-state-dot" />
              {stateLabel}
            </span>
          </div>

          <p>{description}</p>
        </div>

        <button
          type="button"
          role="switch"
          aria-label={title}
          aria-checked={enabled}
          aria-disabled={!available}
          disabled={!available}
          className="as-toggle"
          data-on={enabled}
          data-emergency={isEmergency}
          onClick={() => {
            if (!available) return;

            if (isRetention && !nextValue) {
              void onSave({ retain_conversations: false });
              return;
            }

            setConfirm(true);
          }}
        >
          <span className="as-toggle-thumb" />
        </button>
      </div>

      {!enforced && (
        <p className="as-control-hint">
          {isRetention
            ? "Saved history requires Owner access."
            : "Runtime enforcement is unavailable. This control cannot be changed."}
        </p>
      )}

      {confirm && (
        <div
          className="as-control-confirm"
          role="group"
          aria-label={"Confirm " + title}
        >
          <div className="as-confirm-header">
            <strong>
              {confirmationTitle}
            </strong>
            <span>Confirmation required</span>
          </div>

          <p>{warning}</p>

          <div className="as-control-actions">
            <button
              type="button"
              className="secondary-button"
              disabled={busy}
              onClick={() => setConfirm(false)}
            >
              Cancel
            </button>

            <button
              type="button"
              className="as-primary"
              disabled={!available}
              onClick={async () => {
                const changes = {
                  [field]: nextValue,
                } as Partial<SecurityPreferences>;

                if (await onSave(changes)) {
                  setConfirm(false);
                }
              }}
            >
              {busy ? "Saving…" : "Confirm change"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function SecuritySettings({
  guest,
  snapshot,
  busy,
  onSave,
}: Props) {
  return (
    <section className="panel as-panel">
      <h2>Security</h2>
      <p className="as-description">
        Manage access and emergency protection.
      </p>

      <SecurityControl
        key={"stop-" + snapshot.revision}
        field="emergency_stop"
        title="Emergency stop"
        description="Immediately denies new cloud AI requests."
        enabled={snapshot.settings.emergency_stop}
        busy={busy}
        editable={snapshot.editable_fields.includes(
          "emergency_stop"
        )}
        enforced={snapshot.security_enforcement_active}
        onSave={onSave}
      />

      <SettingRow
        title="Owner authentication"
        description="Required to access your private workspace."
      >
        <Status tone={guest ? "neutral" : "good"}>
          {guest ? "Owner required" : "Protected"}
        </Status>
      </SettingRow>

      <SettingRow
        title="Tool permissions"
        description="Scoped access and action approvals."
      >
        <Status>Coming later</Status>
      </SettingRow>

      <Notice>
        Emergency stop cannot recall requests already sent.
        Use the confirmation control above to change its state.
      </Notice>
    </section>
  );
}

function PrivacySettings({
  guest,
  snapshot,
  busy,
  onSave,
}: Props) {
  return (
    <section className="panel as-panel">
      <h2>Privacy</h2>
      <p className="as-description">
        Manage cloud authorization and local conversation retention.
      </p>

      <SecurityControl
        key={"cloud-" + snapshot.revision}
        field="cloud_enabled"
        title="Cloud AI access"
        description="Allow individually approved public or synthetic requests."
        enabled={snapshot.settings.cloud_enabled}
        busy={busy}
        editable={snapshot.editable_fields.includes(
          "cloud_enabled"
        )}
        enforced={snapshot.security_enforcement_active}
        onSave={onSave}
      />

      <SecurityControl
        key={"history-" + snapshot.revision}
        field="retain_conversations"
        title="Conversation history"
        description="Save completed conversations to your private local database."
        enabled={snapshot.settings.retain_conversations}
        busy={busy}
        editable={!guest && snapshot.editable_fields.includes(
          "retain_conversations"
        )}
        enforced={!guest}
        onSave={onSave}
      />

      <Notice>
        Private and sensitive data remain blocked from cloud AI.
        Content checks are not perfect, so review every request.
        Emergency stop is managed in Security.
      </Notice>

      <Notice>
        {guest
          ? "Saved history requires Owner access."
          : "Disabling history stops new saves. Previously saved conversations can still be reopened or deleted. Local storage is not application-encrypted."}
      </Notice>
    </section>
  );
}

function StorageSettings({
  storage,
}: {
  storage: StorageResponse | null;
}) {
  return (
    <section className="panel as-panel">
      <h2>Local storage</h2>

      <p className="as-description">
        Database health and persistence information.
      </p>

      {!storage ? (
        <p className="as-muted">
          Storage diagnostics unavailable or loading.
        </p>
      ) : (
        <>
          <div className="as-storage-overview">
            <div className="as-storage-metric">
              <Database size={20} />
              <span>Database engine</span>
              <strong>SQLite</strong>
            </div>

            <div className="as-storage-metric">
              <Activity size={20} />
              <span>Database integrity</span>
              <strong>
                <Status tone={storage.integrity === "ok" ? "good" : "warning"}>
                  {storage.integrity === "ok" ? "Healthy" : "Failed"}
                </Status>
              </strong>
            </div>

            <div className="as-storage-metric">
              <ShieldCheck size={20} />
              <span>Schema compatibility</span>
              <strong>
                <Status tone={
                  storage.schema_version === storage.expected_schema_version
                    ? "good" : "warning"
                }>
                  {storage.schema_version === storage.expected_schema_version
                    ? "Up to date" : "Mismatch"}
                </Status>
              </strong>
            </div>
          </div>

          <SettingRow title="Schema version">
            v{storage.schema_version}
          </SettingRow>

          <SettingRow title="Expected schema">
            v{storage.expected_schema_version}
          </SettingRow>

          <SettingRow title="Storage location">
            <Status tone={storage.local_only ? "good" : "neutral"}>
              {storage.local_only ? "Local device" : "Unknown"}
            </Status>
          </SettingRow>

          <SettingRow title="Application-level encryption">
            <Status tone={storage.encrypted_by_application ? "good" : "warning"}>
              {storage.encrypted_by_application ? "Enabled" : "Not enabled"}
            </Status>
          </SettingRow>
        </>
      )}

      <Notice>
        Database files use restrictive filesystem permissions.
        That is not the same as encryption. Backup and restore
        controls currently remain available through the
        terminal workflow.
      </Notice>
    </section>
  );
}

export default function SettingsWorkspace(
  props: Props & { guest?: boolean }
) {
  const guest = props.guest === true;
  const safeProps: Props = props;
  const {
    snapshot,
    busy,
    section,
    onSectionChange,
  } = props;

  const [providers, setProviders] =
    useState<ProvidersResponse | null>(null);

  const [storage, setStorage] =
    useState<StorageResponse | null>(null);

  const [audit, setAudit] =
    useState<AuditResponse | null>(null);

  const [refresh, setRefresh] = useState(0);

  const [diagnosticError, setDiagnosticError] = useState("");

  const [auditBusy, setAuditBusy] = useState(false);

  useEffect(() => {
    if (guest) return;

    let active = true;

    Promise.allSettled([
      getProviders(),
      getStorage(),
      getAudit(),
    ]).then(result => {
      if (!active) return;

      setProviders(
        result[0].status === "fulfilled"
          ? result[0].value : null
      );

      setStorage(
        result[1].status === "fulfilled"
          ? result[1].value : null
      );

      setAudit(
        result[2].status === "fulfilled"
          ? result[2].value : null
      );

      setDiagnosticError(
        result.some(item => item.status === "rejected")
          ? "Some diagnostics could not be loaded."
          : ""
      );
    });

    return () => {
      active = false;
    };
  }, [snapshot.revision, refresh, guest]);

  async function loadOlder() {
    if (guest || !audit?.next_before_id || auditBusy) return;

    setAuditBusy(true);

    try {
      const older = await getAudit(audit.next_before_id);

      setAudit(previous => previous ? ({
        events: [...previous.events, ...older.events],
        next_before_id: older.next_before_id,
      }) : older);
    } catch {
      setDiagnosticError("Unable to load older activity.");
    } finally {
      setAuditBusy(false);
    }
  }

  return (
    <div className="as-workspace">
      <div className="page-heading">
        <div className="eyebrow">CONTROL CENTER</div>
        <h1>Settings</h1>
        <p>
          Manage your preferences, providers and local workspace.
        </p>
      </div>

      <div className="as-layout">
        <nav className="panel as-navigation"
          aria-label="Settings sections"
        >
          {SECTIONS.map(item => (
            <button
              key={item.id}
              type="button"
              disabled={busy}
              data-active={section === item.id}
              aria-current={
                section === item.id ? "page" : undefined
              }
              onClick={() => onSectionChange(item.id)}
            >
              <item.icon size={18} />
              <span>{item.title}</span>
            </button>
          ))}

          <div className="as-revision">
            {guest ? "Guest preview" : `Local revision ${snapshot.revision}`}
          </div>
        </nav>

        <div className="as-content">
          <div className="as-content-toolbar">
            <span className="as-muted">
              {guest
                ? "Guest preview · No private settings loaded"
                : `Last saved: ${formatTime(snapshot.updated_at)}`}
            </span>

            <button
              className="secondary-button"
              disabled={busy || auditBusy}
              onClick={async () => {
                if (await props.onReload()) {
                  setRefresh(value => value + 1);
                }
              }}
            >
              <RefreshCw size={14} />
              Reload settings
            </button>
          </div>

          {guest && (
            <Notice>
              Guest preferences are temporary.
              Live AI, private settings, credentials and
              security changes require Owner access.
            </Notice>
          )}

          {diagnosticError && (
            <p className="as-error" role="alert">
              {diagnosticError}
            </p>
          )}

          <div hidden={section !== "general"}>
            <GeneralSettings key={snapshot.revision} {...safeProps} />

          </div>

          {section === "ai" && (
            <ProviderSettings
              providers={providers}
            />
          )}

          {section === "integrations" && (
            <IntegrationPanel guest={guest}/>
          )}

          {section === "security" && (
            <SecuritySettings {...safeProps} />
          )}

          {section === "privacy" && (
            <PrivacySettings {...safeProps} />
          )}

          {section === "storage" && (
            <StorageSettings storage={storage} />
          )}

          {section === "audit" && (
            <section className="panel as-panel">
              <h2>Audit log</h2>

              <p className="as-description">
                Metadata-only settings events. Messages,
                API keys and passwords are not included.
              </p>

              {!audit ? (
                <p className="as-muted">
                  Activity unavailable or loading.
                </p>
              ) : audit.events.length === 0 ? (
                <div className="as-audit-empty">
                  <Activity size={28} />
                  <strong>No settings activity recorded yet</strong>
                  <p>Settings changes will appear here.</p>
                </div>
              ) : (
                <div className="as-audit-list">
                  <div className="as-audit-summary">
                    <strong>Settings activity</strong>
                    <span>{audit.events.length} loaded events</span>
                  </div>
                  {audit.events.map(event => (
                    <article key={event.id}>
                      <div className="as-audit-icon">
                        <Activity size={18} />
                      </div>
                      <div className="as-audit-copy">
                        <strong>
                          {event.event_type === "settings.updated"
                            ? "Settings updated"
                            : event.event_type === "emergency_stop.enabled"
                              ? "Emergency stop activated"
                              : event.event_type === "emergency_stop.disabled"
                                ? "Emergency stop deactivated"
                                : event.event_type.replaceAll(".", " ").replaceAll("_", " ")}
                        </strong>
                        <p>
                          Revision {event.settings_revision}
                        </p>
                      </div>
                      <time>{formatTime(event.created_at)}</time>
                    </article>
                  ))}
                </div>
              )}

              {audit?.next_before_id && (
                <button
                  type="button"
                  className="secondary-button"
                  disabled={auditBusy || busy}
                  onClick={() => void loadOlder()}
                >
                  {auditBusy ? "Loading…" : "Load older events"}
                </button>
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
