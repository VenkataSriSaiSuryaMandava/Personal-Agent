"use client";

import type { ComponentPropsWithoutRef } from "react";
import {
  CheckCircle2,
  AlertCircle,
  X,
} from "lucide-react";

export function Button({
  className = "",
  variant = "secondary",
  type = "button",
  ...props
}: ComponentPropsWithoutRef<"button"> & {
  variant?: "primary" | "secondary" | "icon";
}) {
  return (
    <button
      {...props}
      type={type}
      className={`aegis-button aegis-button-${variant} ${className}`}
    />
  );
}

export function WorkspaceSkeleton({
  label = "Loading workspace preferences",
}: {
  label?: string;
}) {
  return (
    <section
      className="aegis-skeleton-layout"
      role="status"
      aria-label={label}
      aria-busy="true"
    >
      <span className="aegis-skeleton-label">{label}…</span>

      <div className="aegis-skeleton-line aegis-skeleton-title" />

      <div className="aegis-skeleton-grid" aria-hidden="true">
        {Array.from({ length: 4 }, (_, index) => (
          <div className="panel" key={index}>
            <div className="aegis-skeleton-line" />
            <div className="aegis-skeleton-line aegis-skeleton-short" />
          </div>
        ))}
      </div>

      <div
        className="panel aegis-skeleton-content"
        aria-hidden="true"
      >
        <div className="aegis-skeleton-line" />
        <div className="aegis-skeleton-line" />
        <div className="aegis-skeleton-line aegis-skeleton-short" />
      </div>
    </section>
  );
}

export function Notification({
  message,
  failed,
  onDismiss,
}: {
  message: string;
  failed: boolean;
  onDismiss: () => void;
}) {
  const Icon = failed ? AlertCircle : CheckCircle2;

  return (
    <div
      className="aegis-notification"
      data-tone={failed ? "error" : "success"}
    >
      <Icon size={20} aria-hidden="true" />

      <div role={failed ? "alert" : "status"}>
        <strong>
          {failed ? "Action required" : "Workspace updated"}
        </strong>
        <p>{message}</p>
      </div>

      <Button
        variant="icon"
        onClick={onDismiss}
        aria-label="Dismiss notification"
      >
        <X size={17} />
      </Button>
    </div>
  );
}
