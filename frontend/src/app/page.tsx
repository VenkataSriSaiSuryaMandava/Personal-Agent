"use client";

import { useState } from "react";
import { PanelLeft, MessageSquare } from "lucide-react";
import AuthGate from "@/components/auth/AuthGate";
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";
import StatusCard from "@/components/dashboard/StatusCard";
import Conversation from "@/components/dashboard/Conversation";
import SystemStatus from "@/components/dashboard/SystemStatus";
import Approvals from "@/components/dashboard/Approvals";
import { navigation, type Workspace } from "@/lib/navigation";

export default function Home() {
  return <AuthGate><Dashboard /></AuthGate>;
}

function Dashboard() {
  const [active, setActive] = useState<Workspace>("overview");
  const [dark, setDark] = useState(true);
  const [collapsed, setCollapsed] = useState(false);
  const current = navigation.find(item => item.id === active)!;

  return <div className="app-shell ac-shell" data-theme={dark ? "dark" : "light"} data-sidebar={collapsed ? "collapsed" : "expanded"}>
    <Sidebar active={active} onNavigate={setActive}/>
    <main className="main-content">
      <div className="ac-topbar-wrap">
        <button className="icon-button ac-sidebar-toggle" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed} onClick={() => setCollapsed(!collapsed)}><PanelLeft size={19}/></button>
        <Header title={current.label} dark={dark} onToggleTheme={() => setDark(!dark)}/>
      </div>
      <div className="workspace-content ac-workspace">
        <div hidden={active !== "chat"}><Conversation /></div>
        {active === "overview" && <>
          <div className="page-heading"><div className="eyebrow">SYSTEM OVERVIEW</div><h1>Your command center.</h1><p>View service status, security controls and available features.</p></div>
          <div className="stats-grid">
            <StatusCard title="AI provider" value="Gemini" description="Gemini conversational AI"/>
            <StatusCard title="Task engine" value="Off" description="Not implemented yet"/>
            <StatusCard title="File access" value="Off" description="Not connected"/>
            <StatusCard title="Execution" value="Off" description="Text responses only"/>
          </div>
          <div className="dashboard-grid"><div className="right-column">
            <section className="panel ac-overview-card"><MessageSquare size={26}/><h2>Start a conversation</h2><p>Ask questions, compare ideas and generate code with the AI assistant.</p><button className="secondary-button" onClick={() => setActive("chat")}>Ask Aegis →</button></section>

          </div><div className="right-column"><SystemStatus/><Approvals onOpen={() => setActive("approvals")}/></div></div>
        </>}
        {active !== "chat" && active !== "overview" && <>
          <div className="page-heading"><h1>{current.label}</h1><p>Manage your {current.label.toLowerCase()} workspace.</p></div>
          <section className="panel placeholder-panel"><current.icon size={42}/><h2>{current.label}</h2><p>This workspace is not connected yet.</p><button className="secondary-button" onClick={() => setActive("overview")}>Return to overview</button></section>
        </>}
      </div>
    </main>
  </div>;
}
