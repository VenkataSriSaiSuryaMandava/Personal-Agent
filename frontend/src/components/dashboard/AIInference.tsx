"use client";

import { workspaceFetch } from "@/lib/session-client";


import { useState, useEffect, useRef } from "react";
import {
  Sparkles,
  ShieldCheck,
  Code,
  Briefcase,
  Calendar,
  Send,
  Lock,
  Check,
  LoaderCircle,
  MessageSquare,
  Trash2,
} from "lucide-react";

import ReactMarkdown from "react-markdown";
import { sendMessage } from "@/lib/api";
import "./AIInference.css";

const prompts = [
  {
    id: "general_knowledge",
    category: "Coding",
    label: "Explain binary search",
    text: "Explain how a binary search algorithm works.",
    icon: Code,
  },
  {
    id: "job_search_demo",
    category: "Career",
    label: "Create a job search plan",
    text: "Create a sample job search plan for a fictional entry-level software engineer named Alex.",
    icon: Briefcase,
  },
  {
    id: "productivity_demo",
    category: "Productivity",
    label: "Plan a productive day",
    text: "Create an example daily productivity schedule for a fictional software engineer.",
    icon: Calendar,
  },
] as const;

type Entry = {
  id: number;
  prompt: string;
  answer: string;
  source: string;
};

export default function AIInference() {
  const [selected, setSelected] = useState("");
  const [message, setMessage] = useState("");
  const [approved, setApproved] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);

  const messagesRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = messagesRef.current;

    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  }, [entries, loading]);

  const current = prompts.find(
    (item) => item.id === selected
  );

  function chooseTask(id: string) {
    setSelected(id);
    setMessage("");
    setApproved(false);
    setError("");
  }

  function updateMessage(value: string) {
    setMessage(value);
    setSelected("");
    setApproved(false);
    setError("");
  }

  async function generate() {
    if (loading) return;

    if (current && !approved) return;

    if (!current && !message.trim()) return;

    setLoading(true);
    setError("");
    setApproved(false);

    try {
      if (current) {
        const response = await workspaceFetch(
          "/api/agent/inference",
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              prompt_id: current.id,
              approved: true,
            }),
            signal: AbortSignal.timeout(35000),
            cache: "no-store",
          }
        );

        if (response.status === 429) {
          throw new Error(
            "Usage limit reached. Try again later."
          );
        }

        if (!response.ok) {
          throw new Error(
            "Cloud inference blocked or unavailable."
          );
        }

        const data = await response.json();

        if (
          data.status !== "completed" ||
          data.provider !== "gemini" ||
          data.transmitted !== true ||
          data.executed !== false ||
          typeof data.message !== "string" ||
          typeof data.model !== "string"
        ) {
          throw new Error("Invalid AI response.");
        }

        setEntries((previous) => [
          ...previous,
          {
            id: Date.now(),
            prompt: current.text,
            answer: data.message,
            source: data.model,
          },
        ]);

        setSelected("");
      } else {
        const localMessage = message.trim();

        const result = await sendMessage(localMessage);

        if (
          result.status !== "preview" ||
          result.transmitted !== false ||
          result.executed !== false ||
          typeof result.message !== "string"
        ) {
          throw new Error("Invalid local response.");
        }

        setEntries((previous) => [
          ...previous,
          {
            id: Date.now(),
            prompt: localMessage,
            answer: "Your message was received locally. Custom AI inference is not enabled yet. Select a quick action to generate an AI response.",
            source: "Local preview",
          },
        ]);

        setMessage("");
      }
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Unable to complete the request."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className={`panel aegis-panel`}>
      <header className="aegis-header">
        <div className="aegis-identity">
          <div className="aegis-logo">
            <Sparkles size={24} />
          </div>

          <div>
            <h2>Aegis Assistant</h2>
            <p>Your personal intelligence workspace</p>
          </div>
        </div>

        <span className="aegis-security">
          <ShieldCheck size={15} />
          Privacy controls
        </span>
      </header>

      <div className="aegis-section">
        <h3>Quick actions</h3>

        <div className="aegis-taskGrid">
          {prompts.map((prompt) => {
            const Icon = prompt.icon;
            const active = selected === prompt.id;

            return (
              <button
                key={prompt.id}
                type="button"
                aria-pressed={active}
                disabled={loading}
                className={
                  active
                    ? `aegis-task aegis-selected`
                    : "aegis-task"
                }
                onClick={() => chooseTask(prompt.id)}
              >
                <div className="aegis-taskTop">
                  <Icon size={20} />
                  {active && <Check size={16} />}
                </div>

                <strong>{prompt.category}</strong>
                <span>{prompt.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="aegis-conversation">
        <div className="aegis-conversationHeader">
          <div>
            <MessageSquare size={17} />
            <strong>Conversation</strong>
          </div>

          {entries.length > 0 && (
            <button
              type="button"
              disabled={loading}
              className="aegis-clear"
              onClick={() => setEntries([])}
            >
              <Trash2 size={15} />
              Clear
            </button>
          )}
        </div>

        {entries.length === 0 && !loading && (
          <div className="aegis-empty">
            <Sparkles size={35} />
            <h3>How can I help you today?</h3>
            <p>
              Choose a quick action or write a message.
            </p>
          </div>
        )}

        <div
          className="aegis-messages"
          ref={messagesRef}
          aria-live="polite"
        >
          {entries.map((entry) => (
            <article
              key={entry.id}
              className="aegis-exchange"
            >
              <div className="aegis-userMessage">
                <span>You</span>
                <p>{entry.prompt}</p>
              </div>

              <div className="aegis-agentMessage">
                <div className="aegis-agentHeading">
                  <Sparkles size={17} />
                  <strong>Aegis</strong>
                  <small>{entry.source}</small>
                </div>

                <div className="aegis-markdown">
                  <ReactMarkdown
                    skipHtml
                    disallowedElements={["a", "img"]}
                    unwrapDisallowed
                  >
                    {entry.answer}
                  </ReactMarkdown>
                </div>
              </div>
            </article>
          ))}

          {loading && (
            <div
              className="aegis-loading"
              role="status"
            >
              <LoaderCircle size={20} />
              {current
                ? "Generating your response..."
                : "Processing local request..."}
            </div>
          )}
        </div>
      </div>

      <form
        className="aegis-composer"
        onSubmit={(event) => {
          event.preventDefault();
          void generate();
        }}
      >
        <textarea
          aria-label="Message Aegis"
          value={current ? current.text : message}
          placeholder="Ask Aegis anything..."
          disabled={loading}
          maxLength={4000}
          rows={3}
          onChange={(event) =>
            updateMessage(event.target.value)
          }
        />

        {current && (
          <div className="aegis-approval">
            <input
              id="cloud-approval"
              type="checkbox"
              checked={approved}
              disabled={loading}
              onChange={(event) =>
                setApproved(event.target.checked)
              }
            />

            <label htmlFor="cloud-approval">
              I approve sending this predefined
              prompt to Gemini.
            </label>
          </div>
        )}

        <div className="aegis-toolbar">
          <div className="aegis-mode">
            <Lock size={14} />

            {current
              ? "Controlled cloud inference"
              : "Local preview · No cloud transmission"}
          </div>

          <button
            type="submit"
            className="aegis-generate"
            aria-busy={loading}
            disabled={
              loading ||
              (current
                ? !approved
                : !message.trim())
            }
          >
            {loading ? (
              <LoaderCircle size={18} />
            ) : current ? (
              <ShieldCheck size={18} />
            ) : (
              <Send size={18} />
            )}

            {loading
              ? "Processing..."
              : current
                ? "Approve & Generate"
                : "Send locally"}
          </button>
        </div>
      </form>

      {error && (
        <div
          role="alert"
          className="aegis-error"
        >
          {error}
        </div>
      )}

      <p className="aegis-footer">
        Custom messages stay local. Cloud AI requires
        approval and an unchanged trusted prompt.
      </p>
    </section>
  );
}
