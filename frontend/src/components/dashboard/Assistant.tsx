"use client";

import { useState } from "react";
import { Sparkles, Send } from "lucide-react";
import { sendMessage } from "@/lib/api";

const suggestions = [
  "Plan my day",
  "Find software engineering jobs",
  "Research a topic",
  "Review my code",
];

export default function Assistant() {
  const [message, setMessage] = useState("");
  const [response, setResponse] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  async function submit() {
    if (!message.trim() || loading) return;

    setLoading(true);
    setError(false);
    setResponse("");

    try {
      const result = await sendMessage(message);

      setResponse(result.message);
      setMessage("");
    } catch {
      setError(true);
      setResponse(
        "Unable to complete the request. Check the local backend connection."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel assistant-panel">
      <div className="panel-heading">
        <h2>AI Assistant</h2>
        <span className="muted">API preview</span>
      </div>

      <div className="assistant-content">
        <div className="assistant-icon">
          <Sparkles size={32} />
        </div>

        <h2>What can I help you with?</h2>

        <p>Your personal AI workspace starts here.</p>

        <div className="suggestion-grid">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              disabled={loading}
              onClick={() => {
                setMessage(suggestion);
                setResponse("");
              }}
            >
              {suggestion}
            </button>
          ))}
        </div>

        {loading && (
          <div role="status" className="notice">
            Processing local request...
          </div>
        )}

        {response && (
          <div
            role={error ? "alert" : "status"}
            className={error ? "notice error-notice" : "notice"}
          >
            {response}
          </div>
        )}
      </div>

      <form
        className="chat-input"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <input
          aria-label="Assistant request"
          value={message}
          maxLength={4000}
          disabled={loading}
          onChange={(event) => {
            setMessage(event.target.value);
          }}
          placeholder="Ask Aegis anything..."
        />

        <button
          type="submit"
          aria-label="Send request"
          disabled={!message.trim() || loading}
        >
          <Send size={18} />
        </button>
      </form>

      <small className="chat-note">
        Local API preview. External AI and execution remain disabled.
      </small>
    </section>
  );
}
