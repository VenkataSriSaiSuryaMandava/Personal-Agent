"use client";

import { ShieldCheck } from "lucide-react";
import { navigation, type Workspace } from "@/lib/navigation";

interface SidebarProps {
  active: Workspace;
  onNavigate: (page: Workspace) => void;
}

export default function Sidebar({
  active,
  onNavigate,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-icon">
          <ShieldCheck size={23} />
        </div>
        <div>
          <strong>Aegis</strong>
          <small>PERSONAL AGENT</small>
        </div>
      </div>

      <nav aria-label="Main navigation">
        <p className="nav-heading">WORKSPACE</p>

        {navigation.map((item) => {
          const Icon = item.icon;

          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              aria-current={active === item.id ? "page" : undefined}
              className={`nav-item ${
                active === item.id ? "active" : ""
              }`}
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <span className="status-dot" />
        Development mode
      </div>
    </aside>
  );
}
