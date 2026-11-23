import { navigation, type Workspace } from "./navigation";

export const SETTINGS_SECTIONS = [
  "general",
  "ai",
  "security",
  "privacy",
  "storage",
  "audit",
] as const;

export type SettingsSection =
  (typeof SETTINGS_SECTIONS)[number];

export type WorkspaceLocation = {
  workspace: Workspace;
  section: SettingsSection;
};

export function readWorkspaceLocation(
  fallback: Workspace = "overview"
): WorkspaceLocation {
  const params = new URLSearchParams(
    window.location.search
  );

  const requestedWorkspace = params.get("workspace");
  const requestedSection = params.get("section");

  const workspace: Workspace = navigation.some(
    item => item.id === requestedWorkspace
  )
    ? requestedWorkspace as Workspace
    : fallback;

  const section: SettingsSection =
    workspace === "settings" &&
    SETTINGS_SECTIONS.some(
      item => item === requestedSection
    )
      ? requestedSection as SettingsSection
      : "general";

  return {
    workspace,
    section,
  };
}

export function writeWorkspaceLocation(
  workspace: Workspace,
  section: SettingsSection = "general",
  replace = false
) {
  const url = new URL(window.location.href);

  url.searchParams.set("workspace", workspace);

  if (workspace === "settings") {
    url.searchParams.set("section", section);
  } else {
    url.searchParams.delete("section");
  }

  const target =
    url.pathname + url.search + url.hash;

  const current =
    window.location.pathname +
    window.location.search +
    window.location.hash;

  if (target === current) {
    return;
  }

  if (replace) {
    window.history.replaceState(null, "", target);
  } else {
    window.history.pushState(null, "", target);
  }
}
