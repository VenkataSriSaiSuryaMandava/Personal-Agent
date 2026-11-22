"use client";

import { Moon, Sun, Shield } from "lucide-react";

interface HeaderProps {
  title: string;
  dark: boolean;
  onToggleTheme: () => void;
}

export default function Header({
  title,
  dark,
  onToggleTheme,
}: HeaderProps) {
  return (
    <header className="topbar">
      <div className="breadcrumb">
        Workspace / <strong>{title}</strong>
      </div>

      <div className="header-actions">
        <span className="mode-label">
          <Shield size={14} />
          Owner workspace
        </span>

        <button
          className="icon-button"
          onClick={onToggleTheme}
          aria-label="Toggle color theme"
        >
          {dark ? <Sun size={19} /> : <Moon size={19} />}
        </button>
      </div>
    </header>
  );
}
