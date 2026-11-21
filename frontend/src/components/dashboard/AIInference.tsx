"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import styles from "./AIInference.module.css";
import { Sparkles, ShieldCheck } from "lucide-react";

const prompts = [
  {
    id: "general_knowledge",
    label: "Explain binary search",
    text: "Explain how a binary search algorithm works.",
  },
  {
    id: "job_search_demo",
    label: "Sample job search plan",
    text: "Create a sample job search plan for a fictional entry-level software engineer named Alex.",
  },
  {
    id: "productivity_demo",
    label: "Sample productivity plan",
    text: "Create an example daily productivity schedule for a fictional software engineer.",
  },
] as const;

export default function AIInference() {
  const [selected, setSelected] =
    useState<string>(prompts[0].id);

  const [approved, setApproved] = useState(false);
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [model, setModel] = useState("");

  const current = prompts.find(
    (item) => item.id === selected
  );

  async function generate() {
    if (!approved || loading || !current) return;

    setLoading(true);
    setApproved(false);
    setAnswer("");
    setError("");
    setModel("");

    try {
      const response = await fetch(
        "/api/agent/inference",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            prompt_id: selected,
            approved: true,
          }),
          signal: AbortSignal.timeout(35000),
          cache: "no-store",
        }
      );

      if (!response.ok) {
        throw new Error("Inference unavailable");
      }

      const data = await response.json();

      if (
        data.status !== "completed" ||
        data.transmitted !== true ||
        data.executed !== false ||
        data.provider !== "gemini" ||
        typeof data.message !== "string" ||
        typeof data.model !== "string"
      ) {
        throw new Error("Invalid response");
      }

      setAnswer(data.message);
      setModel(data.model);

    } catch {
      setError(
        "Inference was blocked or unavailable. Check your local configuration and provider quota."
      );

    } finally {
      setLoading(false);
    }
  }

  return (
    <section className={`panel ${styles.panel}`}>
      <div className="panel-heading">
        <h2>AI Assistant</h2>
        <Sparkles size={20} />
      </div>

      <p className="muted">
        Controlled Gemini inference using trusted prompts.
      </p>

      <label htmlFor="trusted-prompt">
        Select a task
      </label>

      <select
        id="trusted-prompt"
        value={selected}
        disabled={loading}
        onChange={(event) => {
          setSelected(event.target.value);
          setApproved(false);
          setAnswer("");
          setError("");
        }}
      >
        {prompts.map((prompt) => (
          <option key={prompt.id} value={prompt.id}>
            {prompt.label}
          </option>
        ))}
      </select>

      <div className={styles.prompt}>
        <strong>Exact text sent to Gemini</strong>
        <p>{current?.text}</p>
      </div>

      <label className={styles.approval}>
        <input
          type="checkbox"
          checked={approved}
          disabled={loading}
          onChange={(event) =>
            setApproved(event.target.checked)
          }
        />

        <span>
          I approve sending this predefined prompt
          to Gemini.
        </span>
      </label>

      <button
        className={styles.generate}
        onClick={() => void generate()}
        disabled={!approved || loading}
      >
        <ShieldCheck size={17} />
        {loading ? "Generating..." : "Approve & Generate"}
      </button>

      {error && (
        <div role="alert" className="notice error-notice">
          {error}
        </div>
      )}

      {answer && (
        <div role="status" className={styles.response}>
          <div className="panel-heading">
            <strong>Gemini response</strong>
            <span className="muted">{model}</span>
          </div>

          <div className={styles.markdown}>
            <ReactMarkdown
              skipHtml
              disallowedElements={["a", "img"]}
              unwrapDisallowed
            >
              {answer}
            </ReactMarkdown>
          </div>
        </div>
      )}
    </section>
  );
}
