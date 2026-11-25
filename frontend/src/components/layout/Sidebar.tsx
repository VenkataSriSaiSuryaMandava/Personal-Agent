"use client";

import { ShieldCheck } from "lucide-react";
import { navigation, type Workspace } from "@/lib/navigation";

interface SidebarProps {
  active: Workspace;
  onNavigate: (page: Workspace) => void;
}

const groups: {
  title: string;
  ids: Workspace[];
}[] = [
  {
    title: "WORKSPACE",
    ids: ["overview", "chat", "tasks", "jobs"],
  },
  {
    title: "PRODUCTIVITY",
    ids: ["email", "calendar", "research", "coding", "browser"],
  },
  {
    title: "SYSTEM",
    ids: ["memory", "approvals", "settings"],
  },
];

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
          <small>PERSONAL AI WORKSPACE</small>
        </div>
      </div>

      <nav aria-label="Main navigation">
        {groups.map(group => (
          <div className="aegis-nav-group" key={group.title}>
            <p className="nav-heading">{group.title}</p>
            {group.ids.map(id => {
              const item = navigation.find(entry => entry.id === id)!;
              const Icon = item.icon;

              return (
                <button
                  key={item.id}
                  type="button"
                  aria-label={item.label}
                  title={item.label}
                  onClick={() => onNavigate(item.id)}
                  aria-current={active === item.id ? "page" : undefined}
                  className={`nav-item ${active === item.id ? "active" : ""}`}
                >
                  <Icon size={17} />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="sidebar-footer">
        <ShieldCheck size={15} />
        Aegis workspace
      </div>
    </aside>
  );
}
