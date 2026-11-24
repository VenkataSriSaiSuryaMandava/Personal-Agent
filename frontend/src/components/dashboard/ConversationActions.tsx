"use client";

import { useEffect, useRef, useState } from "react";
import {
  MoreHorizontal,
  Pencil,
  Trash2,
} from "lucide-react";

type Props = {
  title: string;
  disabled: boolean;
  onRename: () => void;
  onDelete: () => void;
};

export default function ConversationActions({
  title,
  disabled,
  onRename,
  onDelete,
}: Props) {
  const [open, setOpen] = useState(false);

  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  const visible = open && !disabled;

  useEffect(() => {
    if (!visible) return;

    function outside(event: PointerEvent) {
      if (
        event.target instanceof Node &&
        !root.current?.contains(event.target)
      ) {
        setOpen(false);
      }
    }

    function keyboard(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    }

    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", keyboard);

    return () => {
      document.removeEventListener(
        "pointerdown",
        outside,
      );

      document.removeEventListener(
        "keydown",
        keyboard,
      );
    };
  }, [visible]);

  function perform(action: () => void) {
    setOpen(false);
    trigger.current?.focus();
    action();
  }

  return (
    <div
      className="ac-action-root"
      ref={root}
      onBlur={event => {
        if (
          !event.currentTarget.contains(
            event.relatedTarget
          )
        ) {
          setOpen(false);
        }
      }}
    >
      <button
        ref={trigger}
        type="button"
        className="ac-action-trigger"
        aria-label={`Actions for ${title}`}
        title="Conversation actions"
        aria-expanded={visible}
        disabled={disabled}
        onClick={() => setOpen(previous => !previous)}
      >
        <MoreHorizontal size={18}/>
      </button>

      {visible && (
        <div
          className="ac-action-menu"
          role="group"
          aria-label="Conversation actions"
        >
          <button
            type="button"
            onClick={() => perform(onRename)}
          >
            <Pencil size={14}/>
            Rename
          </button>

          <button
            type="button"
            className="ac-delete-action"
            onClick={() => perform(onDelete)}
          >
            <Trash2 size={14}/>
            Delete
          </button>
        </div>
      )}
    </div>
  );
}
