"use client";

import { useState } from "react";
import { Sparkles, Send } from "lucide-react";

const suggestions = [
  "Plan my day",
  "Find software engineering jobs",
  "Research a topic",
  "Review my code",
];

export default function Assistant() {
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState(false);

  return (
    <section className="panel assistant-panel">
      <div className="panel-heading">
        <h2>AI Assistant</h2>
        <span className="muted">Not connected</span>
      </div>

      <div className="assistant-content">
        <div className="assistant-icon">
          <Sparkles size={32} />
        </div>

        <h2>What can I help you with?</h2>

        <p>
          Your personal AI workspace starts here.
        </p>

        <div className="suggestion-grid">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              onClick={() => {
                setMessage(suggestion);
                setPreview(false);
              }}
            >
              {suggestion}
            </button>
          ))}
        </div>

        {preview && (
          <div role="status" className="notice">
            AI provider integration is not available yet.
            Your request has not been transmitted or executed.
          </div>
        )}
      </div>

      <form
        className="chat-input"
        onSubmit={(event) => {
          event.preventDefault();
          if (message.trim()) setPreview(true);
        }}
      >
        <input
          aria-label="Assistant request"
          value={message}
          onChange={(event) => {
            setMessage(event.target.value);
            setPreview(false);
          }}
          placeholder="Ask Aegis anything..."
        />

        <button
          type="submit"
          aria-label="Preview request"
          disabled={!message.trim()}
        >
          <Send size={18} />
        </button>
      </form>

      <small className="chat-note">
        Interface preview. No requests are sent to external services.
      </small>
    </section>
  );
}
