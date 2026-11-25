"use client";

import { Moon, Sun, Shield } from "lucide-react";
import type { Workspace } from "@/lib/navigation";
import CommandPalette from "@/components/ui/CommandPalette";
import { Button } from "@/components/ui/WorkspaceUI";

interface HeaderProps {
  title: string;
  dark: boolean;
  themeDisabled?: boolean;
  guest?: boolean;
  onToggleTheme: () => void;
  onNavigate: (workspace: Workspace) => void;
  commandDisabled?: boolean;
}

export default function Header({
  title,
  dark,
  themeDisabled = false,
  guest = false,
  onToggleTheme,
  onNavigate,
  commandDisabled,
}: HeaderProps) {
  return (
    <header className="topbar">
      <div className="breadcrumb">
        Workspace / <strong>{title}</strong>
      </div>

      <div className="header-actions">
        <CommandPalette
          onNavigate={onNavigate}
          disabled={commandDisabled}
        />
        <span className="mode-label">
          <Shield size={14} />
          {guest ? "Public workspace" : "Owner workspace"}
        </span>

        <Button
          variant="icon"
          disabled={themeDisabled}
          onClick={onToggleTheme}
          aria-label="Toggle color theme"
        >
          {dark ? <Sun size={19} /> : <Moon size={19} />}
        </Button>
      </div>
    </header>
  );
}
