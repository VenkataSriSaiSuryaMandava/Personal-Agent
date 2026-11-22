"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Copy, Check, LoaderCircle, Plus, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./Conversation.css";

type Turn = { user: string; assistant: string };
const SUGGESTIONS = [
  ["Understand a concept", "Explain distributed systems with examples."],
  ["Write better code", "Show a Python binary search implementation and explain its complexity."],
  ["Plan a project", "Create a fictional software project plan with milestones."],
  ["Compare options", "Compare REST and GraphQL in a Markdown table."],
];
const bytes = (text: string) => new TextEncoder().encode(text).length;

function selectContext(turns: Turn[], draft: string, include: boolean): Turn[] {
  if (!include) return [];
  let remaining = 16000 - bytes(draft);
  const result: Turn[] = [];
  for (const turn of turns.slice(-3).reverse()) {
    const length = bytes(turn.user) + bytes(turn.assistant);
    if (length > remaining) break;
    result.unshift(turn);
    remaining -= length;
  }
  return result;
}

function errorMessage(status: number) {
  if (status === 401) return "Your session expired. Sign in again.";
  if (status === 403) return "Cloud chat is disabled or this content was blocked by privacy policy. Review the text and server settings.";
  if (status === 429) return "Usage limit reached (3 requests/minute, 30/day shared with trusted prompts). Try later.";
  if (status === 413 || status === 422) return "Your message or context is invalid or too long.";
  return "Gemini or the local backend is unavailable. No automatic retry was performed.";
}

export default function Conversation() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [include, setInclude] = useState(true);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState<number | null>(null);
  const busyRef = useRef(false);
  const messages = useRef<HTMLDivElement>(null);
  const controller = useRef<AbortController | null>(null);
  const text = draft.trim();
  const history = selectContext(turns, text, include);
  const ready = Boolean(text && text.length <= 4000 && bytes(text) <= 16000 && !busy);

  useEffect(() => {
    if (messages.current) messages.current.scrollTop = messages.current.scrollHeight;
  }, [turns, pending]);
  useEffect(() => () => controller.current?.abort(), []);

  function update(value: string) {
    setDraft(value);
    setError("");
  }

  function newChat() {
    if (busyRef.current) return;
    setTurns([]);
    update("");
    setCopied(null);
  }

  async function send() {
    if (!ready || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setPending(text);
    setError("");
    const abort = new AbortController();
    controller.current = abort;
    const timeout = window.setTimeout(() => abort.abort(), 45000);
    try {
      const response = await fetch("/api/agent/conversation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        signal: abort.signal,
        body: JSON.stringify({ message: text, history, classification: "public", approved: true }),
      });
      if (response.status === 401) window.dispatchEvent(new Event("aegis-session-expired"));
      if (!response.ok) throw new Error(errorMessage(response.status));
      const data = await response.json();
      if (data.status !== "completed" || data.provider !== "gemini" || data.model !== "gemini-3.1-flash-lite" ||
          data.transmitted !== true || data.executed !== false || typeof data.message !== "string" || !data.message.trim()) {
        throw new Error("Invalid model response.");
      }
      setTurns(previous => [...previous, { user: text, assistant: data.message }]);
      update("");
    } catch (failure) {
      setError(abort.signal.aborted ? "Request ended or timed out. Gemini may still have received it. Check before retrying." :
        failure instanceof Error ? failure.message : "Unable to generate a response.");
    } finally {
      window.clearTimeout(timeout);
      controller.current = null;
      busyRef.current = false;
      setBusy(false);
      setPending("");
    }
  }

  async function copy(index: number, answer: string) {
    try {
      await navigator.clipboard.writeText(answer);
      setCopied(index);
    } catch {
      setError("Unable to copy. Select and copy the response manually.");
    }
  }

  return (
    <section className="ac-panel" aria-label="Aegis conversation">
      <header className="ac-header">
        <div className="ac-brand"><span className="ac-logo"><Sparkles size={22} /></span><div>
          <h2>Aegis Assistant</h2><p>Gemini 3.1 Flash-Lite · Cloud assistant</p>
        </div></div>
        <button type="button" className="ac-button" disabled={busy} onClick={newChat}><Plus size={16}/> New chat</button>
      </header>
      <div className="ac-scroll" ref={messages} aria-live="polite" aria-busy={busy}>
        {turns.length === 0 && !pending && <div className="ac-welcome">
          <span className="ac-hero-icon"><Sparkles size={30}/></span>
          <span className="ac-eyebrow">YOUR INTELLIGENCE WORKSPACE</span>
          <h1>What can I help you with?</h1>
          <p>Explore ideas, understand concepts, solve problems and write better code.</p>
          <div className="ac-suggestions">{SUGGESTIONS.map(([title, prompt]) => <button key={title} type="button" onClick={() => update(prompt)}>
            <strong>{title}</strong><span>{prompt}</span>
          </button>)}</div>
        </div>}
        {turns.map((turn, index) => <article className="ac-turn" key={index}>
          <div className="ac-user"><span>You</span><p>{turn.user}</p></div>
          <div className="ac-answer">
            <div className="ac-answer-head"><Sparkles size={18}/><strong>Aegis</strong><small>Gemini</small></div>
            <div className="ac-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml disallowedElements={["a", "img", "input"]} unwrapDisallowed components={{
              table: ({ children }) => <div className="ac-table-wrap"><table>{children}</table></div>,
            }}>{turn.assistant}</ReactMarkdown></div>
            <button className="ac-copy" type="button" onClick={() => void copy(index, turn.assistant)}>{copied === index ? <Check size={14}/> : <Copy size={14}/>} {copied === index ? "Copied" : "Copy response"}</button>
          </div>
        </article>)}
        {pending && <article className="ac-turn"><div className="ac-user"><span>You</span><p>{pending}</p></div><div className="ac-loading" role="status"><LoaderCircle size={18}/> Generating response…</div></article>}
      </div>
      <form className="ac-composer" onSubmit={event => { event.preventDefault(); void send(); }}>
        <textarea aria-label="Message Aegis" placeholder="Ask Aegis anything non-private…" value={draft} maxLength={4000} rows={3} disabled={busy} onChange={event => update(event.target.value)} onKeyDown={event => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); }
        }}/>
        <div className="ac-privacy-bar">
          <span>Gemini cloud AI · Send only non-private content</span>
          <label>
            <input
              type="checkbox"
              checked={include}
              disabled={busy}
              onChange={event => setInclude(event.target.checked)}
            />
            Include recent context
          </label>
        </div>
        {error && <p className="ac-error" role="alert">{error}</p>}
        <div className="ac-toolbar"><span>{draft.length}/4000 · Enter to send · Shift+Enter for newline</span>
          <button type="submit" disabled={!ready} className="ac-send" aria-label="Send message to Gemini">{busy ? <LoaderCircle size={18}/> : <ArrowUp size={18}/>} {busy ? "Generating" : "Send"}</button>
        </div>
      </form>
      <footer className="ac-footer">Text-only AI · Sending shares your message and enabled context with Gemini · No automatic tool execution</footer>
    </section>
  );
}
