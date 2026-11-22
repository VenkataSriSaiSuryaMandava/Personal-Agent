"use client";

import { useRef, useState } from "react";
import { ArrowRight, Copy, Check, LayoutDashboard, MessageSquare, Moon, ShieldCheck, Sparkles, Sun } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import StatusCard from "./StatusCard";
import "./Conversation.css";

type ExampleId = "search" | "systems" | "project";
type Sample = { prompt: string; answer: string };
const examples: { id: ExampleId; title: string; description: string }[] = [
  { id: "search", title: "Compare algorithms", description: "Binary vs. linear search, with Python code" },
  { id: "systems", title: "Understand a concept", description: "Distributed systems and design trade-offs" },
  { id: "project", title: "Plan a project", description: "A fictional project plan and milestones" },
];

export default function DemoWorkspace() {
  const [active, setActive] = useState<"overview" | "chat">("overview");
  const [dark, setDark] = useState(true);
  const [sample, setSample] = useState<Sample | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const inFlight = useRef(false);

  async function selectExample(id: ExampleId) {
    if (inFlight.current) return;
    inFlight.current = true;
    setActive("chat");
    setBusy(true);
    setError("");
    setSample(null);
    setCopied(false);
    try {
      const response = await fetch(`/api/demo/example?id=${id}`, {
        cache: "no-store", signal: AbortSignal.timeout(10000),
      });
      if (!response.ok) throw new Error("Demo unavailable");
      const body = await response.json();
      if (body?.mode !== "recorded_demo" || typeof body.prompt !== "string" || typeof body.answer !== "string") {
        throw new Error("Invalid example");
      }
      setSample({ prompt: body.prompt, answer: body.answer });
    } catch {
      setError("The demo is temporarily unavailable. Please try again.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  function reset() {
    if (inFlight.current) return;
    setSample(null);
    setError("");
    setCopied(false);
  }

  async function copy() {
    if (!sample) return;
    try {
      await navigator.clipboard.writeText(sample.answer);
      setCopied(true);
    } catch {
      setError("Unable to copy automatically. Select the response to copy it.");
    }
  }

  return <div className="app-shell ac-shell" data-theme={dark ? "dark" : "light"}>
    <aside className="sidebar">
      <div className="brand"><div className="brand-icon"><ShieldCheck size={23}/></div><div><strong>Aegis</strong><small>PUBLIC DEMO</small></div></div>
      <nav aria-label="Demo navigation">
        <button className={`nav-item ${active === "overview" ? "active" : ""}`} aria-label="Overview" aria-current={active === "overview" ? "page" : undefined} onClick={() => setActive("overview")}><LayoutDashboard size={18}/><span>Overview</span></button>
        <button className={`nav-item ${active === "chat" ? "active" : ""}`} aria-label="AI Assistant" aria-current={active === "chat" ? "page" : undefined} onClick={() => setActive("chat")}><MessageSquare size={18}/><span>AI Assistant</span></button>
      </nav>
      <div className="sidebar-footer"><ShieldCheck size={14}/> Public demo · v0.1</div>
    </aside>
    <main className="main-content">
      <header className="topbar"><div className="breadcrumb">Aegis / <strong>{active === "overview" ? "Overview" : "AI Assistant"}</strong></div><div className="header-actions"><span className="mode-label">Public demo</span><button className="icon-button" aria-label="Toggle color theme" onClick={() => setDark(!dark)}>{dark ? <Sun size={19}/> : <Moon size={19}/>}</button></div></header>
      <div className="workspace-content ac-workspace">
        <div className="notice" style={{ marginBottom: 20, marginTop: 0 }}>Portfolio preview · Fixed, recorded examples served by FastAPI. No live Gemini calls, personal data or external actions.</div>
        {active === "overview" ? <>
          <div className="page-heading"><div className="eyebrow">AEGIS AI · PUBLIC DEMO</div><h1>Your command center.</h1><p>A preview of the personal intelligence workspace.</p></div>
          <div className="stats-grid">
            <StatusCard title="Workspace" value="Demo" description="Isolated public preview"/>
            <StatusCard title="AI examples" value="3" description="Recorded sample responses"/>
            <StatusCard title="Private data" value="None" description="No owner information"/>
            <StatusCard title="Execution" value="Off" description="No tools or external actions"/>
          </div>
          <div className="dashboard-grid"><section className="panel ac-overview-card"><Sparkles size={26}/><h2>Explore the assistant</h2><p>Try sample responses with Markdown tables, code and structured explanations.</p><button className="secondary-button" onClick={() => setActive("chat")}>Open AI Assistant <ArrowRight size={15} style={{ display: "inline" }}/></button></section><section className="panel"><div className="panel-heading"><h2>Demo capabilities</h2></div><div className="service-row">Frontend <small>Next.js</small></div><div className="service-row">Backend <small>FastAPI</small></div><div className="service-row">Inference <small>Recorded examples</small></div><div className="service-row">Owner routes <small>Disabled</small></div></section></div>
        </> : <section className="ac-panel" aria-label="Aegis demo conversation">
          <header className="ac-header"><div className="ac-brand"><span className="ac-logo"><Sparkles size={22}/></span><div><h2>Aegis Assistant</h2><p>Recorded response demonstration</p></div></div><button className="ac-button" disabled={busy} onClick={reset}>New example</button></header>
          <div className="ac-scroll" aria-live="polite" aria-busy={busy}>
            {!sample && !busy && <div className="ac-welcome"><span className="ac-hero-icon"><Sparkles size={30}/></span><h1>Explore Aegis AI</h1><p>Choose one of the examples below.</p></div>}
            {busy && <p className="ac-loading" role="status">Loading recorded example…</p>}
            {sample && <article className="ac-turn"><div className="ac-user"><span>Example prompt</span><p>{sample.prompt}</p></div><div className="ac-answer"><div className="ac-answer-head"><Sparkles size={18}/><strong>Aegis</strong><small>Recorded example</small></div><div className="ac-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml disallowedElements={["a", "img", "input"]} unwrapDisallowed components={{table: ({children}) => <div className="ac-table-wrap"><table>{children}</table></div>}}>{sample.answer}</ReactMarkdown></div><button className="ac-copy" onClick={() => void copy()}>{copied ? <Check size={14}/> : <Copy size={14}/>} {copied ? "Copied" : "Copy response"}</button></div></article>}
          </div>
          <div className="ac-composer"><div className="ac-suggestions" style={{ marginTop: 0 }}>{examples.map(example => <button key={example.id} disabled={busy} onClick={() => void selectExample(example.id)}><strong>{example.title}</strong><span>{example.description}</span></button>)}</div>{error && <p className="ac-error" role="alert">{error}</p>}</div>
          <footer className="ac-footer">Fixed examples only · No custom text or cloud transmission</footer>
        </section>}
      </div>
    </main>
  </div>;
}
