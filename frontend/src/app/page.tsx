"use client";

import { useState } from "react";
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";
import StatusCard from "@/components/dashboard/StatusCard";
import AIInference from "@/components/dashboard/AIInference";
import SystemStatus from "@/components/dashboard/SystemStatus";
import Approvals from "@/components/dashboard/Approvals";
import { navigation, type Workspace } from "@/lib/navigation";

export default function Home() {
  const [active, setActive] = useState<Workspace>("overview");
  const [dark, setDark] = useState(true);

  const current = navigation.find(
    (item) => item.id === active
  )!;

  return (
    <div className="app-shell" data-theme={dark ? "dark" : "light"}>
      <Sidebar
        active={active}
        onNavigate={setActive}
      />

      <main className="main-content">
        <Header
          title={current.label}
          dark={dark}
          onToggleTheme={() => setDark(!dark)}
        />

        <div className="workspace-content">
          {active === "overview" ? (
            <>
              <div className="page-heading">
                <div className="eyebrow">
                  YOUR PERSONAL WORKSPACE
                </div>

                <h1>Your command center.</h1>

                <p>
                  Intelligence, productivity and control
                  in one place.
                </p>
              </div>

              <div className="stats-grid">
                <StatusCard
                  title="Active tasks"
                  value="0"
                  description="No execution engine"
                />

                <StatusCard
                  title="Pending approvals"
                  value="0"
                  description="No pending requests"
                />

                <StatusCard
                  title="Applications"
                  value="0"
                  description="Job tracking not connected"
                />

                <StatusCard
                  title="AI provider"
                  value="Gemini"
                  description="See live system status"
                />
              </div>

              <div className="dashboard-grid">
                <div className="right-column">
                  
                  <AIInference />
                </div>

                <div className="right-column">
                  <SystemStatus />
                  <Approvals
                    onOpen={() => setActive("approvals")}
                  />
                </div>
              </div>
            </>
          ) : active === "chat" ? (
            <>
              <div className="page-heading">
                <h1>AI Assistant</h1>
                <p>Interact with your personal agent.</p>
              </div>

              <div className="right-column">
                  
                  <AIInference />
                </div>
            </>
          ) : (
            <>
              <div className="page-heading">
                <h1>{current.label}</h1>
                <p>Manage your {current.label.toLowerCase()} workspace.</p>
              </div>

              <section className="panel placeholder-panel">
                <current.icon size={42} />

                <h2>{current.label}</h2>

                <p>
                  This workspace will be connected in
                  an upcoming development milestone.
                </p>

                <button
                  className="secondary-button"
                  onClick={() => setActive("overview")}
                >
                  Return to overview
                </button>
              </section>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
