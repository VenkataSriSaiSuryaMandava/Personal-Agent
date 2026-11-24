export type Theme = "dark" | "light" | "system";

export type StartupWorkspace =
  | "overview"
  | "chat"
  | "settings";

export type ResponseStyle =
  | "balanced"
  | "concise"
  | "detailed";

export type GeneralPreferences = {
  theme: Theme;
  startup_workspace: StartupWorkspace;
  response_style: ResponseStyle;
};

export type SecurityPreferences = {
  cloud_enabled: boolean;
  emergency_stop: boolean;
  retain_conversations: boolean;
};

export type ApplicationSettings = GeneralPreferences & {
  primary_provider: "gemini" | "groq";
  fallback_provider: "gemini" | "groq";
  fallback_enabled: boolean;
  cloud_enabled: boolean;
  retain_conversations: boolean;
  emergency_stop: boolean;
};

export type SettingsSnapshot = {
  settings: ApplicationSettings;
  revision: number;
  updated_at: number;
  editable_fields: string[];
  security_enforcement_active: boolean;
};

export type ProviderStatus = {
  provider: "gemini" | "groq";
  configured: boolean;
  implemented: boolean;
  model: string | null;
  status: string;
  live_verified: boolean;
};

export type ProvidersResponse = {
  providers: ProviderStatus[];
  primary_provider: string;
  fallback_provider: string;
  fallback_enabled: boolean;
  fallback_implemented: boolean;
};

export type StorageResponse = {
  database: string;
  schema_version: number;
  expected_schema_version: number;
  integrity: "ok" | "failed";
  local_only: boolean;
  encrypted_by_application: boolean;
};

export type AuditEvent = {
  id: number;
  event_type: string;
  settings_revision: number;
  created_at: number;
};

export type AuditResponse = {
  events: AuditEvent[];
  next_before_id: number | null;
};

const BASE = "/api/agent/settings";

async function request<T>(
  suffix = "",
  init: RequestInit = {}
): Promise<T> {
  const response = await fetch(BASE + suffix, {
    ...init,
    cache: "no-store",
    credentials: "same-origin",
    signal: AbortSignal.timeout(25000),
  });

  if (response.status === 401) {
    window.dispatchEvent(
      new Event("aegis-session-expired")
    );
  }

  if (!response.ok) {
    const messages: Record<number, string> = {
      401: "Session expired. Sign in again.",
      403: "Settings request denied.",
      409: "Settings changed elsewhere. Reload settings before saving.",
      422: "Invalid or unsupported settings.",
      503: "Local settings service unavailable.",
    };

    throw new Error(
      messages[response.status] ??
      "Unable to complete settings request."
    );
  }

  return response.json() as Promise<T>;
}

function validateSnapshot(
  data: SettingsSnapshot
): SettingsSnapshot {
  const value = data?.settings;

  if (
    !value ||
    !Number.isSafeInteger(data.revision) ||
    data.revision < 1 ||
    !Number.isSafeInteger(data.updated_at) ||
    !Array.isArray(data.editable_fields) ||
    !["dark", "light", "system"].includes(value.theme) ||
    !["overview", "chat", "settings"].includes(
      value.startup_workspace
    ) ||
    !["balanced", "concise", "detailed"].includes(
      value.response_style
    ) ||
    !["gemini", "groq"].includes(value.primary_provider) ||
    !["gemini", "groq"].includes(value.fallback_provider) ||
    typeof value.cloud_enabled !== "boolean" ||
    typeof value.emergency_stop !== "boolean" ||
    typeof value.retain_conversations !== "boolean" ||
    typeof value.fallback_enabled !== "boolean" ||
    typeof data.security_enforcement_active !== "boolean"
  ) {
    throw new Error("Invalid settings response.");
  }

  return data;
}

export async function getSettings() {
  return validateSnapshot(
    await request<SettingsSnapshot>()
  );
}

export async function updateSettings(
  changes: Partial<GeneralPreferences & SecurityPreferences>,
  revision: number
) {
  return validateSnapshot(
    await request<SettingsSnapshot>("", {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        expected_revision: revision,
        changes,
      }),
    })
  );
}

export async function resetSettings(revision: number) {
  return validateSnapshot(
    await request<SettingsSnapshot>("/reset", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        expected_revision: revision,
      }),
    })
  );
}

export function getProviders() {
  return request<ProvidersResponse>("/providers");
}

export function getStorage() {
  return request<StorageResponse>("/storage");
}

export function getAudit(beforeId?: number) {
  const query = new URLSearchParams({ limit: "25" });

  if (beforeId !== undefined) {
    query.set("before_id", String(beforeId));
  }

  return request<AuditResponse>(
    "/audit?" + query.toString()
  );
}
