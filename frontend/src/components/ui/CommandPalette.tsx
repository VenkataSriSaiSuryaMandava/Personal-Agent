"use client";

import {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  Search,
  ArrowRight,
  X,
} from "lucide-react";

import {
  navigation,
  type Workspace,
} from "@/lib/navigation";

import { Button } from "./WorkspaceUI";

const aliases: Partial<Record<Workspace, string>> = {
  overview: "home dashboard command center",
  chat: "conversation assistant ai",
  tasks: "todo productivity deadlines",
  jobs: "career resume applications discovery matching",
  email: "mail drafts messages",
  calendar: "schedule events agenda",
  research: "notes knowledge sources",
  coding: "code repositories programming",
  browser: "web bookmarks browsing",
  memory: "knowledge diagnostics",
  approvals: "permissions review decisions",
  settings: "preferences theme security providers storage",
};

export default function CommandPalette({
  onNavigate,
  disabled = false,
}: {
  onNavigate: (workspace: Workspace) => void;
  disabled?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);

  const matches = navigation.filter(item => {
    const text = `${item.label} ${item.id} ${aliases[item.id] ?? ""}`;
    return text.toLowerCase().includes(query.trim().toLowerCase());
  });

  const current = Math.min(
    selected,
    Math.max(0, matches.length - 1)
  );

  function open() {
    if (disabled || dialog.current?.open) return;

    setQuery("");
    setSelected(0);

    dialog.current?.showModal();
    input.current?.focus();
  }

  function close() {
    dialog.current?.close();
  }

  function choose(workspace: Workspace) {
    close();
    onNavigate(workspace);
  }

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if (
        disabled ||
        event.repeat ||
        event.isComposing ||
        event.altKey ||
        event.shiftKey ||
        !(event.metaKey || event.ctrlKey) ||
        event.key.toLowerCase() !== "k"
      ) {
        return;
      }

      event.preventDefault();

      if (dialog.current?.open) {
        dialog.current.close();
      } else {
        setQuery("");
        setSelected(0);
        dialog.current?.showModal();
        input.current?.focus();
      }
    }

    window.addEventListener("keydown", shortcut);

    return () => {
      window.removeEventListener("keydown", shortcut);
    };
  }, [disabled]);

  return (
    <>
      <button
        ref={trigger}
        className="aegis-command-trigger"
        type="button"
        aria-label="Search workspaces"
        aria-haspopup="dialog"
        aria-keyshortcuts="Control+K Meta+K"
        disabled={disabled}
        onClick={open}
      >
        <Search size={17} />
        <span>Search workspaces</span>
        <kbd>⌘ / Ctrl K</kbd>
      </button>

      <dialog
        ref={dialog}
        className="aegis-command-dialog"
        aria-label="Workspace command palette"
        onClose={() => trigger.current?.focus()}
        onClick={event => {
          if (event.target === event.currentTarget) close();
        }}
      >
        <div className="aegis-command-content">
          <div className="aegis-command-search">
            <Search size={21} aria-hidden="true" />

            <input
              ref={input}
              aria-label="Find a workspace"
              placeholder="Go to any workspace…"
              role="combobox"
              aria-autocomplete="list"
              aria-expanded="true"
              aria-controls="aegis-command-results"
              aria-activedescendant={
                matches.length
                  ? `aegis-command-${matches[current].id}`
                  : undefined
              }
              value={query}
              onChange={event => {
                setQuery(event.target.value);
                setSelected(0);
              }}
              onKeyDown={event => {
                if (event.key === "ArrowDown") {
                  event.preventDefault();
                  setSelected(
                    Math.min(current + 1, matches.length - 1)
                  );
                } else if (event.key === "ArrowUp") {
                  event.preventDefault();
                  setSelected(Math.max(0, current - 1));
                } else if (
                  event.key === "Enter" &&
                  matches[current]
                ) {
                  event.preventDefault();
                  choose(matches[current].id);
                }
              }}
            />

            <Button
              variant="icon"
              onClick={close}
              aria-label="Close command palette"
            >
              <X size={20} />
            </Button>
          </div>

          <div className="aegis-command-caption">
            WORKSPACES
          </div>

          <div
            id="aegis-command-results"
            className="aegis-command-results"
            role="listbox"
            aria-label="Matching workspaces"
          >
            {matches.map((item, index) => {
              const Icon = item.icon;

              return (
                <div
                  id={`aegis-command-${item.id}`}
                  key={item.id}
                  role="option"
                  aria-selected={index === current}
                  className="aegis-command-result"
                  onMouseEnter={() => setSelected(index)}
                  onMouseDown={event => event.preventDefault()}
                  onClick={() => choose(item.id)}
                >
                  <Icon size={18} aria-hidden="true" />
                  <span>{item.label}</span>
                  <ArrowRight size={15} aria-hidden="true" />
                </div>
              );
            })}

            {!matches.length && (
              <p className="aegis-command-empty" role="status">
                No matching workspaces.
              </p>
            )}
          </div>

          <div className="aegis-command-footer">
            <span>↑ ↓ Navigate</span>
            <span>Enter Open</span>
            <span>Esc Close</span>
          </div>
        </div>
      </dialog>
    </>
  );
}
