"use client";

import { useEffect, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  CalendarDays,
} from "lucide-react";

import type { WorkspaceRecord } from "@/lib/workspaces";

function dateKey(date: Date) {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

export default function CalendarBoard({
  records,
  selected,
  onSelect,
  onCreate,
  incomplete,
  busy,
}: {
  records: WorkspaceRecord[];
  selected: string;
  onSelect: (value: string) => void;
  onCreate: (value: string) => void;
  incomplete: boolean;
  busy: boolean;
}) {
  const [month, setMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });

  const [today, setToday] = useState(
    () => dateKey(new Date()),
  );

  useEffect(() => {
    const timer = window.setInterval(() => {
      setToday(dateKey(new Date()));
    }, 30000);

    return () => window.clearInterval(timer);
  }, []);

  const [view, setView] = useState<
    "month" | "week" | "day"
  >("month");

  const [anchor, setAnchor] = useState(
    () => new Date(),
  );

  const firstDay = month.getDay();

  const totalDays = new Date(
    month.getFullYear(),
    month.getMonth() + 1,
    0,
  ).getDate();

  const cells = Math.ceil(
    (firstDay + totalDays) / 7,
  ) * 7;

  function move(direction: number) {
    if (view === "month") {
      const next = new Date(
        month.getFullYear(),
        month.getMonth() + direction,
        1,
      );

      setMonth(next);
      setAnchor(next);
      onSelect("");
      return;
    }

    const next = new Date(
      anchor.getFullYear(),
      anchor.getMonth(),
      anchor.getDate() +
        direction * (view === "week" ? 7 : 1),
    );

    setAnchor(next);
    setMonth(new Date(
      next.getFullYear(),
      next.getMonth(),
      1,
    ));

    onSelect(dateKey(next));
  }

  function changeView(next: "month" | "week" | "day") {
    setView(next);

    const date = selected
      ? new Date(selected + "T12:00:00")
      : new Date(
          month.getFullYear(),
          month.getMonth(),
          1,
        );

    setAnchor(date);

    if (next !== "month") {
      onSelect(dateKey(date));
    }
  }

  const weekStart = new Date(
    anchor.getFullYear(),
    anchor.getMonth(),
    anchor.getDate() - anchor.getDay(),
  );

  const agendaDates = view === "day"
    ? [anchor]
    : Array.from({ length: 7 }, (_, index) =>
        new Date(
          weekStart.getFullYear(),
          weekStart.getMonth(),
          weekStart.getDate() + index,
        ),
      );

  return (
    <section className="panel wx-calendar">
      <div className="wx-section-heading">
        <div>
          <h2>
            {month.toLocaleDateString(undefined, {
              month: "long",
              year: "numeric",
            })}
          </h2>

          <p className="muted">
            {Intl.DateTimeFormat().resolvedOptions().timeZone}
          </p>
        </div>

        <div className="fw-actions">
          <button
            type="button"
            className="secondary-button"
            aria-label={"Previous " + view}
            onClick={() => move(-1)}
          >
            <ChevronLeft size={18}/>
          </button>

          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              const now = new Date();

              setMonth(new Date(
                now.getFullYear(), now.getMonth(), 1,
              ));

              setAnchor(now);
              onSelect(today);
            }}
          >
            Today
          </button>

          <button
            type="button"
            className="secondary-button"
            aria-label={"Next " + view}
            onClick={() => move(1)}
          >
            <ChevronRight size={18}/>
          </button>
        </div>
      </div>

      <div className="wx-view-tabs" aria-label="Calendar view">
        {(["month", "week", "day"] as const).map(option => (
          <button
            type="button"
            className="secondary-button"
            key={option}
            aria-pressed={view === option}
            data-active={view === option}
            onClick={() => changeView(option)}
          >
            {option}
          </button>
        ))}
      </div>

      {view === "month" ? (
      <div className="wx-calendar-grid">
        {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
          .map(day => (
            <div className="wx-weekday" key={day}>
              {day}
            </div>
          ))}

        {Array.from({ length: cells }, (_, index) => {
          const day = index - firstDay + 1;

          if (day < 1 || day > totalDays) {
            return (
              <div className="wx-day-blank" key={index}/>
            );
          }

          const date = dateKey(new Date(
            month.getFullYear(),
            month.getMonth(),
            day,
          ));

          const events = records.filter(record =>
            record.scheduled_at &&
            dateKey(new Date(record.scheduled_at)) === date,
          );

          return (
            <button
              type="button"
              key={index}
              className="wx-day"
              data-today={date === today}
              data-selected={date === selected}
              aria-pressed={date === selected}
              aria-label={
                date + ", " + events.length + " loaded events"
              }
              onClick={() => onSelect(date)}
            >
              <strong>{day}</strong>

              {events.slice(0, 2).map(event => (
                <span key={event.id} className="wx-calendar-event">
                  {event.title}
                </span>
              ))}

              {events.length > 2 && (
                <small>+{events.length - 2} more</small>
              )}
            </button>
          );
        })}
      </div>

      ) : (
        <div className="wx-calendar-agenda" data-view={view}>
          {agendaDates.map(date => {
            const key = dateKey(date);

            const events = records.filter(record =>
              record.scheduled_at &&
              dateKey(new Date(record.scheduled_at)) === key,
            ).sort((a, b) =>
              a.scheduled_at.localeCompare(b.scheduled_at),
            );

            return (
              <section key={key} className="wx-agenda-day">
                <button
                  type="button"
                  className="secondary-button"
                  aria-pressed={selected === key}
                  onClick={() => onSelect(key)}
                >
                  {date.toLocaleDateString(undefined, {
                    weekday: "short",
                    month: "short",
                    day: "numeric",
                  })}
                </button>

                {events.length ? events.map(event => (
                  <article className="wx-agenda-event" key={event.id}>
                    <strong>{event.title}</strong>
                    <small>
                      {new Date(event.scheduled_at)
                        .toLocaleTimeString(undefined, {
                          hour: "numeric",
                          minute: "2-digit",
                        })}
                    </small>
                  </article>
                )) : (
                  <p className="muted">No events</p>
                )}

                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => onCreate(key)}
                >
                  + Event
                </button>
              </section>
            );
          })}
        </div>
      )}

      <div className="wx-section-heading">
        <p className="muted">
          {incomplete
            ? "Calendar shows loaded events only. Load more records to include additional events."
            : "Local calendar events · No external synchronization"}
        </p>

        <button
          className="secondary-button"
          type="button"
          disabled={busy}
          onClick={() => onCreate(selected || today)}
        >
          <CalendarDays size={16}/>
          Add event
        </button>
      </div>
    </section>
  );
}
