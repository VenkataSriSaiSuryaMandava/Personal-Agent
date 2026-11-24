"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Copy, Check, LoaderCircle, Plus, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  listConversations,
  openConversation,
  renameConversation,
  deleteConversation,
  validConversationId,
  type ConversationSummary,
} from "@/lib/conversations";

import {
  readActiveConversation,
  rememberActiveConversation,
} from "@/lib/conversation-location";

import ConversationActions from "./ConversationActions";
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

function errorMessage(status: number, detail?: unknown) {
  if (status === 401) {
    return "Your session expired. Sign in again.";
  }

  if (status === 403) {
    return "Cloud chat is disabled or this content was blocked by privacy policy. Review the text and server settings.";
  }

  if (status === 429) {
    return detail === "Provider quota exceeded"
      ? "Gemini's usage limit has been reached. Try again later."
      : "AI request limit reached. Please try again later.";
  }

  if (status === 413 || status === 422) {
    return "Your message or context is invalid or too long.";
  }

  if (status === 409 || status === 404) {
    return "Saved conversation changed. Reopen it or start a new chat.";
  }

  if (status === 504) {
    return "Gemini did not respond in time. Your message has been preserved.";
  }

  if (status === 503) {
    if (detail === "Provider temporarily unavailable") {
      return "Gemini is temporarily unavailable. Your message has been preserved. Try again shortly.";
    }

    if (detail === "Usage storage unavailable") {
      return "Local AI usage tracking is unavailable. Your message has been preserved.";
    }

    if (detail === "Local backend is unavailable") {
      return "The local backend is unavailable or the request timed out. Check the connection before retrying.";
    }
  }

  return "Unable to generate a response. Your message has been preserved.";
}

export default function Conversation({
  guest = false,
  retain = false,
}: {
  guest?: boolean;
  retain?: boolean;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [savedChats, setSavedChats] =
    useState<ConversationSummary[]>([]);

  const [activeId, setActiveId] =
    useState<string | null>(null);

  const [savedCount, setSavedCount] = useState(0);

  const [historyExpanded, setHistoryExpanded] =
    useState(true);

  const activeTitle = savedChats.find(
    chat => chat.id === activeId
  )?.title;

  const [historyBusy, setHistoryBusy] = useState(!guest);

  const [historyError, setHistoryError] = useState("");

  const [saveNotice, setSaveNotice] = useState("");

  const [nextOffset, setNextOffset] =
    useState<number | null>(null);

  const historyOperation = useRef(false);
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
  const ready = Boolean(!guest && text && text.length <= 4000 && bytes(text) <= 16000 && !busy && !historyBusy);

  useEffect(() => {
    if (messages.current) messages.current.scrollTop = messages.current.scrollHeight;
  }, [turns, pending]);
  useEffect(() => () => controller.current?.abort(), []);

  useEffect(() => {
    if (guest) return;

    let active = true;
    historyOperation.current = true;

    async function restore() {
      try {
        const result = await listConversations();

        if (!active) return;

        setSavedChats(result.conversations);
        setNextOffset(result.next_offset);
        setHistoryError("");

        const id = readActiveConversation();

        if (!id) return;

        try {
          const saved = await openConversation(id);

          if (!active) return;

          setTurns(saved.turns.map(turn => ({
            user: turn.user,
            assistant: turn.assistant,
          })));

          setActiveId(saved.id);
          setSavedCount(saved.turns.length);
          setSaveNotice("Saved conversation restored.");

          setSavedChats(previous => {
            if (previous.some(chat => chat.id === saved.id)) {
              return previous;
            }

            return [{
              id: saved.id,
              title: saved.title,
              created_at: saved.created_at,
              updated_at: saved.updated_at,
            }, ...previous];
          });

        } catch (failure) {
          if (!active) return;

          if (
            failure instanceof Error &&
            failure.message === "Conversation no longer exists."
          ) {
            rememberActiveConversation(null);
            setHistoryError(
              "Previous conversation no longer exists."
            );
          } else {
            setHistoryError(
              "Unable to restore previous conversation. Reopen it from history."
            );
          }
        }

      } catch {
        if (active) {
          setHistoryError(
            "Unable to load saved conversations."
          );
        }
      } finally {
        if (active) {
          historyOperation.current = false;
          setHistoryBusy(false);
        }
      }
    }

    void restore();

    return () => {
      active = false;
      historyOperation.current = false;
    };
  }, [guest]);

  async function refreshHistory(offset = 0) {
    if (guest) return;

    try {
      const result = await listConversations(offset);

      setSavedChats(previous => {
        if (offset === 0) return result.conversations;

        const known = new Set(
          previous.map(chat => chat.id)
        );

        return [
          ...previous,
          ...result.conversations.filter(
            chat => !known.has(chat.id)
          ),
        ];
      });

      setNextOffset(result.next_offset);
      setHistoryError("");

    } catch {
      setHistoryError(
        "Unable to refresh conversation history."
      );
    }
  }

  async function manageHistory(
    action: () => Promise<void>
  ) {
    if (
      guest ||
      busyRef.current ||
      historyOperation.current
    ) return;

    historyOperation.current = true;
    setHistoryBusy(true);
    setHistoryError("");

    try {
      await action();
    } catch {
      setHistoryError(
        "Unable to complete the history operation."
      );
    } finally {
      historyOperation.current = false;
      setHistoryBusy(false);
    }
  }

  function confirmDiscard() {
    return !(
      draft.trim() ||
      turns.length > savedCount
    ) || window.confirm(
      "Discard unsaved messages or draft?"
    );
  }

  function reopen(id: string) {
    if (!confirmDiscard()) return;

    void manageHistory(async () => {
      const result = await openConversation(id);

      setTurns(result.turns.map(turn => ({
        user: turn.user,
        assistant: turn.assistant,
      })));

      setActiveId(result.id);
      rememberActiveConversation(result.id);
      setSavedCount(result.turns.length);
      setSaveNotice("");
      setCopied(null);
      update("");
    });
  }

  function rename(chat: ConversationSummary) {
    const title = window.prompt(
      "Conversation title",
      chat.title
    )?.trim();

    if (!title || title.length > 120) return;

    void manageHistory(async () => {
      await renameConversation(chat.id, title);
      await refreshHistory();
    });
  }

  function remove(chat: ConversationSummary) {
    if (!window.confirm(
      "Delete this conversation and its saved messages?"
    )) return;

    void manageHistory(async () => {
      await deleteConversation(chat.id);

      if (activeId === chat.id) {
        setTurns([]);
        setActiveId(null);
        rememberActiveConversation(null);
        setSavedCount(0);
        setSaveNotice("");
        setCopied(null);
        update("");
      }

      await refreshHistory();
    });
  }

  function update(value: string) {
    setDraft(value);
    setError("");
  }

  function newChat() {
    if (
      busyRef.current ||
      historyOperation.current ||
      !confirmDiscard()
    ) return;

    setTurns([]);
    setActiveId(null);

    if (!guest) {
      rememberActiveConversation(null);
    }
    setSavedCount(0);
    setSaveNotice("");
    update("");
    setCopied(null);
  }

  async function send() {
    if (
      guest || !ready ||
      busyRef.current || historyOperation.current
    ) return;
    busyRef.current = true;
    setBusy(true);
    setPending(text);
    setError("");
    const persist =
      retain && turns.length === savedCount;

    const abort = new AbortController();
    controller.current = abort;
    const timeout = window.setTimeout(() => abort.abort(), 45000);
    try {
      const response = await fetch("/api/agent/conversation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        signal: abort.signal,
        body: JSON.stringify({
          message: text,
          history,
          classification: "public",
          approved: true,
          persist,
          conversation_id: persist ? activeId : null,
          expected_turn_count: persist ? savedCount : 0,
        }),
      });
      if (response.status === 401) window.dispatchEvent(new Event("aegis-session-expired"));
      if (!response.ok) {
        const failure = await response.json().catch(() => null);

        throw new Error(
          errorMessage(response.status, failure?.detail)
        );
      }
      const data = await response.json();
      if (data.status !== "completed" || data.provider !== "gemini" || data.model !== "gemini-3.1-flash-lite" ||
          data.transmitted !== true || data.executed !== false || typeof data.message !== "string" || !data.message.trim()) {
        throw new Error("Invalid model response.");
      }
      setTurns(previous => [...previous, { user: text, assistant: data.message }]);
      update("");

      if (
        persist &&
        data.persisted === true &&
        validConversationId(data.conversation_id)
      ) {
        setActiveId(data.conversation_id);
        rememberActiveConversation(data.conversation_id);
        setSavedCount(previous => previous + 1);
        setSaveNotice("Conversation saved locally.");

        await refreshHistory();

      } else {
        setSaveNotice(
          persist
            ? "Response received, but not saved. Refresh history before retrying storage."
            : "This response is not saved. Start a new chat to resume saving."
        );
      }

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
    <div
      className="ac-history-layout"
      data-history-expanded={historyExpanded}
      data-guest={guest}
    >
      {!guest && (
        <aside
          className="ac-history"
          aria-label="Saved conversations"
        >
          <div className="ac-history-heading">
            <strong>Conversations</strong>
            <button
              type="button"
              className="ac-button ac-history-toggle"
              aria-expanded={historyExpanded}
              aria-controls="ac-saved-conversations"
              onClick={() => setHistoryExpanded(
                previous => !previous
              )}
            >
              {historyExpanded ? "Hide" : "Show"}
            </button>
          </div>

          <div
            id="ac-saved-conversations"
            className="ac-history-content"
          >
          <p className="ac-history-status">
            {retain
              ? "Local history enabled"
              : "History saving disabled"}
          </p>

          <button
            type="button"
            className="ac-button"
            disabled={busy || historyBusy}
            onClick={() => void manageHistory(
              () => refreshHistory()
            )}
          >
            Refresh
          </button>

          {historyError && (
            <p className="ac-error" role="alert">
              {historyError}
            </p>
          )}

          {!savedChats.length &&
            !historyError && !historyBusy && (
            <p className="ac-history-status">
              No saved conversations yet.
            </p>
          )}

          <div
            className="ac-history-list"
            aria-label="Conversation history"
          >
            {savedChats.map(chat => (
              <div
                key={chat.id}
                className="ac-history-item"
                data-active={activeId === chat.id}
              >
                <div className="ac-history-row">
                  <button
                    type="button"
                    className="ac-history-title"
                    disabled={busy || historyBusy}
                    aria-current={
                      activeId === chat.id
                        ? "true"
                        : undefined
                    }
                    onClick={() => reopen(chat.id)}
                    title={chat.title}
                  >
                    {chat.title}
                  </button>

                  <ConversationActions
                    title={chat.title}
                    disabled={busy || historyBusy}
                    onRename={() => rename(chat)}
                    onDelete={() => remove(chat)}
                  />
                </div>
              </div>
            ))}
          </div>

          {nextOffset !== null && (
            <button
              type="button"
              className="ac-button"
              disabled={busy || historyBusy}
              onClick={() => void manageHistory(
                () => refreshHistory(nextOffset)
              )}
            >
              Load more
            </button>
          )}
          </div>
        </aside>
      )}

    <section
      className="ac-panel"
      aria-label="Aegis conversation"
    >
      <header className="ac-header">
        <div className="ac-brand"><span className="ac-logo"><Sparkles size={22} /></span><div>
          <h2 title={activeTitle ?? "Aegis Assistant"}>
            {activeTitle ?? "Aegis Assistant"}
          </h2><p>{guest ? "AI unavailable in Guest mode" : "Gemini 3.1 Flash-Lite · Cloud assistant"}</p>
        </div></div>
        <button type="button" className="ac-button" disabled={busy || historyBusy} onClick={newChat}><Plus size={16}/> New chat</button>
      </header>
      <div className="ac-scroll" ref={messages} aria-live="polite" aria-busy={busy || historyBusy} tabIndex={0}>
        {historyBusy && turns.length === 0 && (
          <div className="ac-loading" role="status">
            <LoaderCircle size={18}/>
            Loading conversation…
          </div>
        )}
        {turns.length === 0 && !pending && !historyBusy && <div className="ac-welcome">
          <span className="ac-hero-icon"><Sparkles size={30}/></span>
          <span className="ac-eyebrow">YOUR INTELLIGENCE WORKSPACE</span>
          <h1>What can I help you with?</h1>
          <p>Explore ideas, understand concepts, solve problems and write better code.</p>
          <div className="ac-suggestions">{SUGGESTIONS.map(([title, prompt]) => <button key={title} type="button" disabled={busy || historyBusy} onClick={() => update(prompt)}>
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
        <textarea aria-label="Message Aegis" placeholder={guest ? "Try the composer — AI requires Owner access" : "Ask Aegis anything non-private…"} value={draft} maxLength={4000} rows={3} disabled={busy || historyBusy} onChange={event => update(event.target.value)} onKeyDown={event => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); }
        }}/>
        <div className="ac-privacy-bar">
          <span>{guest ? "AI access requires Owner Login" : "Gemini cloud AI · Send only non-private content"}</span>
          <label>
            <input
              type="checkbox"
              checked={include}
              disabled={busy || historyBusy}
              onChange={event => setInclude(event.target.checked)}
            />
            Include recent context
          </label>
        </div>
        {!guest && saveNotice && (
          <p className="ac-history-status" role="status">
            {saveNotice}
          </p>
        )}

        {error && <p className="ac-error" role="alert">{error}</p>}
        <div className="ac-toolbar"><span>{draft.length}/4000 · Enter to send · Shift+Enter for newline</span>
          <button type="submit" disabled={!ready} className="ac-send" aria-label="Send message to Gemini">{busy ? <LoaderCircle size={18}/> : <ArrowUp size={18}/>} {busy ? "Generating" : "Send"}</button>
        </div>
      </form>
      <footer className="ac-footer">Text-only AI · Sending shares your message and enabled context with Gemini · No automatic tool execution</footer>
    </section>
    </div>
  );
}
