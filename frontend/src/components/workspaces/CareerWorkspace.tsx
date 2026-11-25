"use client";

import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import {
  BriefcaseBusiness,
  UserRound,
  Files,
  FileUp,
  ShieldCheck,
  GraduationCap,
  SlidersHorizontal,
  Link2,
  Code,
} from "lucide-react";

import FunctionalWorkspace from "./FunctionalWorkspace";

import {
  getProfile,
  saveProfile,
  listResumes,
  getResume,
  uploadResume,
  mutateResume,
  downloadResume,
  type CareerProfile,
  type ProfileSnapshot,
  type Resume,
  type ResumeDetail,
} from "@/lib/career";

import "./CareerWorkspace.css";

type Section = "applications" | "profile" | "documents";

type StringField = {
  [K in keyof CareerProfile]:
    CareerProfile[K] extends string ? K : never;
}[keyof CareerProfile];

const PROFILE_FIELDS: {
  key: StringField;
  label: string;
  max: number;
  multiline?: boolean;
}[] = [
  { key: "full_name", label: "Full name", max: 300 },
  { key: "headline", label: "Professional headline", max: 300 },
  { key: "email", label: "Email", max: 300 },
  { key: "phone", label: "Phone", max: 300 },
  { key: "location", label: "Current location", max: 300 },
  { key: "summary", label: "Professional summary", max: 8000, multiline: true },
  { key: "education", label: "Education", max: 12000, multiline: true },
  { key: "experience", label: "Work experience", max: 20000, multiline: true },
  { key: "projects", label: "Projects and accomplishments", max: 12000, multiline: true },
  { key: "work_authorization", label: "Work authorization", max: 1000 },
  { key: "linkedin_url", label: "LinkedIn profile URL", max: 2000 },
  { key: "portfolio_url", label: "Portfolio URL", max: 2000 },
  { key: "github_url", label: "GitHub profile URL", max: 2000 },
];

function errorMessage(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Career operation failed.";
}

function Feedback({
  error, notice,
}: {
  error: string;
  notice: string;
}) {
  return (
    <>
      {error && (
        <p className="notice error-notice" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="notice" role="status">{notice}</p>
      )}
    </>
  );
}

function ProfilePanel() {
  const [snapshot, setSnapshot] =
    useState<ProfileSnapshot | null>(null);

  const [lists, setLists] = useState({
    skills: "",
    target_roles: "",
    target_locations: "",
  });

  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const mounted = useRef(false);
  const operation = useRef(false);

  function apply(result: ProfileSnapshot) {
    setSnapshot(result);

    setLists({
      skills: result.profile.skills.join(", "),
      target_roles: result.profile.target_roles.join(", "),
      target_locations: result.profile.target_locations.join(", "),
    });
  }

  useEffect(() => {
    let active = true;
    mounted.current = true;

    getProfile()
      .then(result => {
        if (active) apply(result);
      })
      .catch(error => {
        if (active) setError(errorMessage(error));
      })
      .finally(() => {
        if (active) setBusy(false);
      });

    return () => {
      active = false;
      mounted.current = false;
    };
  }, []);

  function change<K extends keyof CareerProfile>(
    key: K,
    value: CareerProfile[K],
  ) {
    setSnapshot(current => current ? {
      ...current,
      profile: {
        ...current.profile,
        [key]: value,
      },
    } : current);
  }

  async function perform(
    action: () => Promise<ProfileSnapshot>,
    success: string,
  ) {
    if (operation.current || busy) return;

    operation.current = true;
    setBusy(true);
    setError("");
    setNotice("");

    try {
      const result = await action();

      if (!mounted.current) return;

      apply(result);
      setNotice(success);

    } catch (failure) {
      if (mounted.current) {
        setError(errorMessage(failure));
      }
    } finally {
      operation.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  async function submit() {
    if (!snapshot) return;

    const split = (value: string) =>
      value.split(/[,\n]/)
        .map(item => item.trim())
        .filter(Boolean);

    await perform(
      () => saveProfile({
        ...snapshot,
        profile: {
          ...snapshot.profile,
          skills: split(lists.skills),
          target_roles: split(lists.target_roles),
          target_locations: split(lists.target_locations),
        },
      }),
      "Career profile saved locally.",
    );
  }

  return (
    <section className="panel fw-form career-panel">
      <div className="career-panel-heading">
        <h2>My Profile</h2>
        <p className="muted">
          Maintain your qualifications and job preferences.
          Information is not sent to cloud AI.
        </p>
      </div>

      <Feedback error={error} notice={notice}/>

      <button
        className="secondary-button"
        disabled={busy}
        onClick={() => {
          if (
            snapshot &&
            !window.confirm("Reload saved profile and discard unsaved edits?")
          ) return;

          void perform(getProfile, "Saved profile reloaded.");
        }}
      >
        Refresh profile
      </button>

      {!snapshot ? (
        <p role="status">
          {busy ? "Loading profile..." : "Profile unavailable."}
        </p>
      ) : (
        <form
          onSubmit={event => {
            event.preventDefault();
            void submit();
          }}
        >
          <fieldset disabled={busy} className="career-fields">
            <section className="career-group career-wide">
              <h3 className="career-group-heading">
                <UserRound size={18}/>
                Personal information
              </h3>
              <div className="career-fields">
            {PROFILE_FIELDS.filter(field => ["full_name", "headline", "email", "phone", "location"].includes(field.key)).map(field => (
              <label
                key={field.key}
                className={field.multiline ? "career-wide" : ""}
              >
                {field.label}
                {field.multiline ? (
                  <textarea
                    rows={3}
                    maxLength={field.max}
                    value={snapshot.profile[field.key]}
                    onChange={event =>
                      change(field.key, event.target.value)
                    }
                  />
                ) : (
                  <input
                    maxLength={field.max}
                    value={snapshot.profile[field.key]}
                    onChange={event =>
                      change(field.key, event.target.value)
                    }
                  />
                )}
              </label>
            ))}

              </div>
            </section>

            <section className="career-group career-wide">
              <h3 className="career-group-heading">
                <GraduationCap size={18}/>
                Professional experience
              </h3>
              <div className="career-fields">
            {PROFILE_FIELDS.filter(field => ["summary", "education", "experience", "projects"].includes(field.key)).map(field => (
              <label
                key={field.key}
                className={field.multiline ? "career-wide" : ""}
              >
                {field.label}
                {field.multiline ? (
                  <textarea
                    rows={3}
                    maxLength={field.max}
                    value={snapshot.profile[field.key]}
                    onChange={event =>
                      change(field.key, event.target.value)
                    }
                  />
                ) : (
                  <input
                    maxLength={field.max}
                    value={snapshot.profile[field.key]}
                    onChange={event =>
                      change(field.key, event.target.value)
                    }
                  />
                )}
              </label>
            ))}

              </div>
            </section>

            <section className="career-group career-wide">
              <h3 className="career-group-heading">
                <Code size={18}/>
                Skills
              </h3>
              <div className="career-fields">
            {([
              ["skills", "Skills"],
              ["target_roles", "Target roles"],
              ["target_locations", "Target locations"],
            ] as const).filter(([key]) => ["skills"].includes(key)).map(([key, label]) => (
              <label key={key} className="career-wide">
                {label} — comma separated
                <textarea
                  rows={2}
                  maxLength={key === "skills" ? 30000 : 9000}
                  value={lists[key]}
                  onChange={event => setLists(previous => ({
                    ...previous,
                    [key]: event.target.value,
                  }))}
                />
              </label>
            ))}

              </div>
            </section>

            <section className="career-group career-wide">
              <h3 className="career-group-heading">
                <SlidersHorizontal size={18}/>
                Job preferences
              </h3>
              <div className="career-fields">
            {([
              ["skills", "Skills"],
              ["target_roles", "Target roles"],
              ["target_locations", "Target locations"],
            ] as const).filter(([key]) => ["target_roles", "target_locations"].includes(key)).map(([key, label]) => (
              <label key={key} className="career-wide">
                {label} — comma separated
                <textarea
                  rows={2}
                  maxLength={key === "skills" ? 30000 : 9000}
                  value={lists[key]}
                  onChange={event => setLists(previous => ({
                    ...previous,
                    [key]: event.target.value,
                  }))}
                />
              </label>
            ))}

            {PROFILE_FIELDS.filter(field => ["work_authorization"].includes(field.key)).map(field => (
              <label
                key={field.key}
                className={field.multiline ? "career-wide" : ""}
              >
                {field.label}
                {field.multiline ? (
                  <textarea
                    rows={3}
                    maxLength={field.max}
                    value={snapshot.profile[field.key]}
                    onChange={event =>
                      change(field.key, event.target.value)
                    }
                  />
                ) : (
                  <input
                    maxLength={field.max}
                    value={snapshot.profile[field.key]}
                    onChange={event =>
                      change(field.key, event.target.value)
                    }
                  />
                )}
              </label>
            ))}

            <label>
              Preferred work arrangement
              <select
                value={snapshot.profile.work_mode}
                onChange={event => change(
                  "work_mode",
                  event.target.value as CareerProfile["work_mode"],
                )}
              >
                <option value="any">Any</option>
                <option value="remote">Remote</option>
                <option value="hybrid">Hybrid</option>
                <option value="onsite">On-site</option>
              </select>
            </label>

            <label>
              Employment type
              <select
                value={snapshot.profile.employment_type}
                onChange={event => change(
                  "employment_type",
                  event.target.value as CareerProfile["employment_type"],
                )}
              >
                <option value="any">Any</option>
                <option value="full_time">Full-time</option>
                <option value="part_time">Part-time</option>
                <option value="contract">Contract</option>
                <option value="internship">Internship</option>
              </select>
            </label>

            <label>
              Sponsorship required
              <select
                value={snapshot.profile.sponsorship_required}
                onChange={event => change(
                  "sponsorship_required",
                  event.target.value as CareerProfile["sponsorship_required"],
                )}
              >
                <option value="unknown">Not specified</option>
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
            </label>

            <label>
              Salary currency
              <input
                maxLength={3}
                value={snapshot.profile.salary_currency}
                onChange={event => change(
                  "salary_currency",
                  event.target.value.toUpperCase(),
                )}
              />
            </label>

            {([
              ["salary_min", "Minimum annual salary"],
              ["salary_max", "Maximum annual salary"],
            ] as const).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  type="number"
                  min={0}
                  max={10000000}
                  step={1}
                  value={snapshot.profile[key] ?? ""}
                  onChange={event => change(
                    key,
                    event.target.value === ""
                      ? null
                      : Number(event.target.value),
                  )}
                />
              </label>
            ))}

              </div>
            </section>

            <section className="career-group career-wide">
              <h3 className="career-group-heading">
                <Link2 size={18}/>
                Professional links
              </h3>
              <div className="career-fields">
            {PROFILE_FIELDS.filter(field => ["linkedin_url", "portfolio_url", "github_url"].includes(field.key)).map(field => (
              <label
                key={field.key}
                className={field.multiline ? "career-wide" : ""}
              >
                {field.label}
                {field.multiline ? (
                  <textarea
                    rows={3}
                    maxLength={field.max}
                    value={snapshot.profile[field.key]}
                    onChange={event =>
                      change(field.key, event.target.value)
                    }
                  />
                ) : (
                  <input
                    maxLength={field.max}
                    value={snapshot.profile[field.key]}
                    onChange={event =>
                      change(field.key, event.target.value)
                    }
                  />
                )}
              </label>
            ))}

              </div>
            </section>

            <div className="career-wide fw-actions">
              <button
                type="submit"
                className="secondary-button fw-primary"
              >
                {busy ? "Saving..." : "Save profile"}
              </button>
            </div>
          </fieldset>
        </form>
      )}
    </section>
  );
}

function DocumentsPanel() {
  const [records, setRecords] = useState<Resume[]>([]);
  const [selected, setSelected] =
    useState<ResumeDetail | null>(null);

  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");

  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const input = useRef<HTMLInputElement>(null);
  const mounted = useRef(false);
  const operation = useRef(false);

  useEffect(() => {
    let active = true;
    mounted.current = true;

    listResumes()
      .then(result => {
        if (active) setRecords(result);
      })
      .catch(error => {
        if (active) setError(errorMessage(error));
      })
      .finally(() => {
        if (active) setBusy(false);
      });

    return () => {
      active = false;
      mounted.current = false;
    };
  }, []);

  async function perform(
    action: () => Promise<void>,
  ) {
    if (busy || operation.current) return;

    operation.current = true;
    setBusy(true);
    setError("");
    setNotice("");

    try {
      await action();
    } catch (failure) {
      if (mounted.current) {
        setError(errorMessage(failure));
      }
    } finally {
      operation.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  function show(result: ResumeDetail) {
    if (!mounted.current) return;
    setSelected(result);
    setText(result.extracted_text);
  }

  async function reload() {
    const result = await listResumes();
    if (mounted.current) setRecords(result);
  }

  async function reconcile() {
    try {
      await reload();
    } catch {
      if (mounted.current) {
        setError("Change saved. Refresh documents to reload the list.");
      }
    }
  }

  function discardAllowed() {
    return !selected ||
      selected.extracted_text === text ||
      window.confirm("Discard unsaved extracted-text edits?");
  }

  return (
    <section className="panel fw-form career-panel">
      <div className="career-panel-heading">
        <h2>Resume library</h2>
        <p className="muted">
          Upload, review and manage your private resume versions.
        </p>
      </div>

      <div className="career-metrics">
        <div className="career-metric">
          <span>Resume versions</span>
          <strong>{records.length} / 20</strong>
        </div>
        <div className="career-metric">
          <span>Active resume</span>
          <strong>
            {records.find(record => record.is_active)?.title
              ?? "Not selected"}
          </strong>
        </div>
      </div>

      <p className="notice">
        Text extraction runs locally. Review the result before
        using it. Image-only PDFs may require manual text entry.
      </p>

      <Feedback error={error} notice={notice}/>

      <form className="career-upload" onSubmit={event => {
        event.preventDefault();

        if (!file || !title.trim() || !discardAllowed()) return;

        void perform(async () => {
          const result = await uploadResume(
            file, title.trim(),
          );

          if (!mounted.current) return;

          show(result);
          setFile(null);
          setTitle("");

          if (input.current) input.current.value = "";

          setNotice("Resume uploaded and parsed locally.");
          await reconcile();
        });
      }}>
        <fieldset disabled={busy} className="career-fields">
          <label>
            Resume version name
            <input
              required
              maxLength={160}
              value={title}
              onChange={event => setTitle(event.target.value)}
            />
          </label>

          <label className="career-file-picker career-wide">
            <FileUp size={30}/>
            <strong>Choose a resume document</strong>
            <span>PDF, DOCX or TXT · Maximum 10 MiB</span>
            <input
              ref={input}
              required
              type="file"
              accept=".pdf,.docx,.txt"
              onChange={event => {
                const chosen = event.target.files?.[0] ?? null;
                setFile(chosen);

                if (chosen) {
                  setTitle(
                    chosen.name.replace(/\.[^.]+$/, "").slice(0, 160),
                  );
                }
              }}
            />
          </label>

          <div className="career-wide fw-actions">
            <button
              type="submit"
              className="secondary-button fw-primary"
              disabled={!file || records.length >= 20}
            >
              {busy ? "Working..." : "Upload and extract text"}
            </button>
          </div>
        </fieldset>
      </form>

      <button
        className="secondary-button"
        disabled={busy}
        onClick={() => {
          if (!discardAllowed()) return;

          void perform(async () => {
            await reload();

            if (mounted.current) {
              setSelected(null);
              setText("");
              setNotice("Documents refreshed.");
            }
          });
        }}
      >
        Refresh documents
      </button>

      {!busy && records.length === 0 && (
        <div className="career-empty">
          <Files size={30}/>
          <h3>No resume versions yet</h3>
          <p className="muted">
            Upload your first resume to build your private document library.
          </p>
        </div>
      )}

      <div className="career-documents">
        {records.map(record => (
          <article
            className="career-document"
            key={record.id}
            data-active={!!record.is_active}
            data-selected={selected?.id === record.id}
          >
            <strong>{record.title}</strong>
            <p className="muted">
              {Math.max(1, Math.round(record.size_bytes / 1024))} KB
              {" · "}
              {record.is_active ? "Active resume" : "Saved version"}
            </p>

            <div className="fw-actions">
              <button
                className="secondary-button"
                disabled={busy}
                onClick={() => {
                  if (!discardAllowed()) return;
                  void perform(async () =>
                    show(await getResume(record.id)),
                  );
                }}
              >
                Review text
              </button>

              <button
                className="secondary-button"
                disabled={busy || !!record.is_active}
                onClick={() => {
                  if (!discardAllowed()) return;

                  void perform(async () => {
                    await mutateResume(record, "activate");

                    if (!mounted.current) return;

                    setSelected(null);
                    setText("");
                    setNotice("Active resume updated.");
                    await reconcile();
                  });
                }}
              >
                Set active
              </button>

              <button
                className="secondary-button"
                disabled={busy}
                onClick={() => void perform(
                  () => downloadResume(
                    record, () => mounted.current,
                  ),
                )}
              >
                Download
              </button>

              <button
                className="secondary-button fw-delete"
                disabled={busy}
                onClick={() => {
                  if (!discardAllowed()) return;

                  if (!window.confirm(
                    "Delete this resume version? Existing backups may still contain it.",
                  )) return;

                  void perform(async () => {
                    await mutateResume(record, "delete");

                    if (!mounted.current) return;

                    setSelected(null);
                    setText("");
                    setNotice("Resume version deleted.");
                    await reconcile();
                  });
                }}
              >
                Delete
              </button>
            </div>
          </article>
        ))}
      </div>

      {selected && (
        <form className="career-review" onSubmit={event => {
          event.preventDefault();

          void perform(async () => {
            const result = await mutateResume(
              selected, "edit", text,
            ) as ResumeDetail;

            if (!mounted.current) return;

            show(result);
            setNotice("Reviewed text saved. Original file unchanged.");
            await reconcile();
          });
        }}>
          <fieldset disabled={busy} className="career-fields">
            <label className="career-wide">
              Extracted text — {selected.title}
              <textarea
                rows={16}
                maxLength={100000}
                value={text}
                onChange={event => setText(event.target.value)}
              />
            </label>

            <div className="career-wide fw-actions">
              <button
                type="submit"
                className="secondary-button fw-primary"
                disabled={text === selected.extracted_text}
              >
                Save reviewed text
              </button>
            </div>
          </fieldset>
        </form>
      )}
    </section>
  );
}

function GuestPreview({ children }: { children: ReactNode }) {
  return (
    <section className="panel career-panel">
      <h2>Fictional career preview</h2>
      <p className="notice">
        Private profile storage and resume uploads are available
        only in the local Owner application.
      </p>
      {children}
    </section>
  );
}

export default function CareerWorkspace({
  guest,
  onAssistant,
}: {
  guest: boolean;
  onAssistant: () => void;
}) {
  const [section, setSection] =
    useState<Section>("applications");

  return (
    <div className="career-workspace">
      <header className="career-header">
        <div>
          <span className="eyebrow">
            {guest ? "GUEST PREVIEW" : "PRIVATE WORKSPACE"}
          </span>
          <div className="career-heading">
            <BriefcaseBusiness size={28}/>
            <h1>Career workspace</h1>
          </div>
          <p className="muted">
            Manage your applications, qualifications and resumes.
          </p>
        </div>
        <span className="career-privacy">
          <ShieldCheck size={15}/>
          {guest ? "Synthetic preview" : "Local and private"}
        </span>
      </header>
      <nav className="career-tabs" aria-label="Career sections">
        {([
          ["applications", "Applications", BriefcaseBusiness],
          ["profile", "My Profile", UserRound],
          ["documents", "Documents", Files],
        ] as const).map(([key, label, Icon]) => (
          <button
            key={key}
            type="button"
            className="secondary-button"
            aria-pressed={section === key}
            onClick={() => setSection(key)}
          >
            <Icon size={16}/>
            {label}
          </button>
        ))}
      </nav>

      <div
        className="career-applications"
        hidden={section !== "applications"}
      >
        <FunctionalWorkspace
          workspace="jobs"
          guest={guest}
          onAssistant={onAssistant}
        />
      </div>

      {section === "profile" && (
        guest ? (
          <GuestPreview>
            <strong>Alex Example — Software Developer</strong>
            <p>Sample skills: Python, SQL, TypeScript.</p>
            <p>Sample preference: Full-time, hybrid.</p>
          </GuestPreview>
        ) : <ProfilePanel/>
      )}

      {section === "documents" && (
        guest ? (
          <GuestPreview>
            <strong>Sample technical resume</strong>
            <p className="muted">
              Fictional preview only. No files are uploaded or stored.
            </p>
          </GuestPreview>
        ) : <DocumentsPanel/>
      )}
    </div>
  );
}
