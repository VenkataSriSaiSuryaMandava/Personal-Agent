"use client";

import {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  Search,
  Building2,
  Bookmark,
  ExternalLink,
  RefreshCw,
  MapPin,
  Settings2,
  BriefcaseBusiness,
} from "lucide-react";

import {
  listSources,
  createSource,
  updateSource,
  deleteSource,
  refreshSource,
  listJobs,
  getJob,
  saveJob,
  safeJobLink,
  type Provider,
  type RefreshReason,
  type Freshness,
  type JobSource,
  type JobListing,
  type JobDetail,
} from "@/lib/discovery";

import {
  EMPLOYERS,
  recognizeBoard,
} from "@/lib/employer-directory";

import JobIntelligence from "./JobIntelligence";

import "./DiscoverPanel.css";

const PROVIDERS: Record<Provider, string> = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
};

const REFRESH_REASONS: Record<RefreshReason, string> = {
  provider_unavailable:
    "Provider unavailable or download rejected. Try again later.",
  response_rejected:
    "Unsupported provider response. Previous jobs preserved.",
  board_limit:
    "Board exceeds 1,000 listings. Previous jobs preserved.",
  cache_limit:
    "Local job storage limit reached. Previous jobs preserved.",
};

const SOURCE_STATUS: Record<JobSource["last_result"], string> = {
  never: "Not fetched",
  success: "Updated",
  failed: "Refresh failed",
  limited: "Storage or board limit reached",
};

function dateLabel(value: number | null) {
  return value === null
    ? "Never"
    : new Date(value * 1000).toLocaleString();
}

function externalSearch(
  provider: "linkedin" | "indeed",
  search: string,
) {
  const url = new URL(
    provider === "linkedin"
      ? "https://www.linkedin.com/jobs/search/"
      : "https://www.indeed.com/jobs",
  );

  url.searchParams.set(
    provider === "linkedin" ? "keywords" : "q",
    search,
  );

  return url.href;
}

export function GuestDiscovery() {
  return (
    <section className="panel career-panel discover-panel">
      <div className="career-panel-heading">
        <h2>Discover opportunities</h2>
        <p className="muted">
          Fictional preview. Live employer sources are available
          only in the private Owner application.
        </p>
      </div>

      {[
        ["Software Engineer", "Example Technologies", "San Francisco"],
        ["Data Engineer", "Sample Analytics", "Remote"],
        ["Full Stack Developer", "Demo Systems", "Seattle"],
      ].map(([title, company, location]) => (
        <article className="discover-job" key={title}>
          <div className="discover-job-heading">
            <Building2 size={24}/>
            <div>
              <h3>{title}</h3>
              <p>{company}</p>
              <p className="muted">{location}</p>
            </div>
          </div>
          <span className="discover-tag">Fictional listing</span>
          <p className="muted">
            Personalized matching is available only in the
            private Owner application.
          </p>
        </article>
      ))}
    </section>
  );
}

export default function DiscoverPanel({
  onSaved,
}: {
  onSaved: () => void;
}) {
  const [sources, setSources] = useState<JobSource[]>([]);
  const [jobs, setJobs] = useState<JobListing[]>([]);
  const [selected, setSelected] = useState<JobDetail | null>(null);

  const [search, setSearch] = useState("");
  const [location, setLocation] = useState("");
  const [freshness, setFreshness] = useState<Freshness>("all");
  const [appliedLocation, setAppliedLocation] = useState("");
  const [appliedFreshness, setAppliedFreshness] =
    useState<Freshness>("all");
  const [provider, setProvider] = useState<Provider | "">("");

  const [appliedSearch, setAppliedSearch] = useState("");
  const [appliedProvider, setAppliedProvider] =
    useState<Provider | "">("");

  const [nextOffset, setNextOffset] =
    useState<number | null>(null);

  const [manage, setManage] = useState(false);
  const [company, setCompany] = useState("");
  const [board, setBoard] = useState("");
  const [fetchOnAdd, setFetchOnAdd] = useState(true);
  const [sourceProvider, setSourceProvider] =
    useState<Provider>("greenhouse");

  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [progress, setProgress] = useState("");

  const mounted = useRef(false);
  const operation = useRef(false);

  useEffect(() => {
    let active = true;

    mounted.current = true;

    Promise.all([
      listSources(),
      listJobs(),
    ]).then(([sourceData, page]) => {
      if (!active) return;

      setSources(sourceData);
      setJobs(page.jobs);
      setNextOffset(page.next_offset);
      setManage(sourceData.length === 0);
    }).catch(failure => {
      if (active) {
        setError(
          failure instanceof Error
            ? failure.message
            : "Discovery unavailable.",
        );
      }
    }).finally(() => {
      if (active) setBusy(false);
    });

    return () => {
      active = false;
      mounted.current = false;
    };
  }, []);

  async function perform(action: () => Promise<void>) {
    if (busy || operation.current) return;

    operation.current = true;
    setBusy(true);
    setError("");
    setNotice("");

    try {
      await action();
    } catch (failure) {
      if (mounted.current) {
        setError(
          failure instanceof Error
            ? failure.message
            : "Discovery operation failed.",
        );
      }
    } finally {
      operation.current = false;

      if (mounted.current) {
        setBusy(false);
        setProgress("");
      }
    }
  }

  async function loadJobs(
    query = appliedSearch,
    filter = appliedProvider,
    offset = 0,
    locationFilter = appliedLocation,
    freshnessFilter = appliedFreshness,
  ) {
    const page = await listJobs(
      query, filter, offset, locationFilter, freshnessFilter,
    );

    if (!mounted.current) return;

    setAppliedSearch(query);
    setAppliedProvider(filter);
    setAppliedLocation(locationFilter);
    setAppliedFreshness(freshnessFilter);

    setJobs(previous => {
      if (!offset) return page.jobs;

      const existing = new Set(
        previous.map(job => job.id),
      );

      return [
        ...previous,
        ...page.jobs.filter(job => !existing.has(job.id)),
      ];
    });

    setNextOffset(page.next_offset);

    if (!offset) setSelected(null);
  }

  async function reload() {
    const result = await listSources();

    if (!mounted.current) return;

    setSources(result);
    await loadJobs();
  }

  async function refreshBoards(
    records: JobSource[],
    force: boolean,
  ) {
    const issues: string[] = [];
    const outcomes = {
      success: 0,
      cached: 0,
      cooldown: 0,
      failed: 0,
      limited: 0,
    };

    const enabled = records.filter(source => source.enabled);

    for (let index = 0; index < enabled.length; index += 3) {
      if (!mounted.current) return;

      setProgress(
        `Refreshing ${index + 1}–${Math.min(
          index + 3, enabled.length,
        )} of ${enabled.length} boards`,
      );

      const results = await Promise.allSettled(
        enabled.slice(index, index + 3)
          .map(source => refreshSource(source, force)),
      );

      for (const [position, result] of results.entries()) {
        const source = enabled[index + position];

        if (result.status === "fulfilled") {
          outcomes[result.value.result] += 1;

          const reason = result.value.reason;

          if (reason && Object.hasOwn(REFRESH_REASONS, reason)) {
            issues.push(
              `${source.company}: ${REFRESH_REASONS[reason]}`,
            );
          }
        } else {
          outcomes.failed += 1;

          issues.push(
            `${source.company}: Refresh denied, busy or unavailable.`,
          );
        }
      }
    }

    if (!mounted.current) return;

    await reload();

    if (mounted.current) {
      setNotice(
        `Updated: ${outcomes.success}. ` +
        `Already current: ${outcomes.cached}. ` +
        `Recently checked: ${outcomes.cooldown}. ` +
        `Failed: ${outcomes.failed}. ` +
        `Limited: ${outcomes.limited}.` +
        (issues.length ? "\n" + issues.join("\n") : ""),
      );
    }
  }

  async function saveOpportunity(job: JobListing) {
    const result = await saveJob(job.id);

    if (!mounted.current) return;

    setJobs(previous => previous.map(item =>
      item.id === job.id
        ? {
            ...item,
            application_id: result.application_id,
          }
        : item,
    ));

    setSelected(previous =>
      previous?.id === job.id
        ? {
            ...previous,
            application_id: result.application_id,
          }
        : previous,
    );

    onSaved();

    setNotice(
      result.created
        ? "Job saved to Applications."
        : "Job already exists in Applications.",
    );
  }

  const enabledCount = sources.filter(
    source => source.enabled,
  ).length;

  const latestRefresh = Math.max(
    0,
    ...sources.map(source => source.last_success_at ?? 0),
  );

  return (
    <section className="panel career-panel discover-panel">
      <div className="discover-heading">
        <div className="career-panel-heading">
          <h2>Discover opportunities</h2>
          <p className="muted">
            Search configured employer boards. Results are cached
            locally and do not cover the entire job market.
          </p>
        </div>

        <button
          className="secondary-button"
          onClick={() => setManage(value => !value)}
          aria-expanded={manage}
        >
          <Settings2 size={16}/>
          Manage sources
        </button>
      </div>

      <div className="career-metrics discover-metrics">
        <div className="career-metric">
          <span>Loaded opportunities</span>
          <strong>{jobs.length}</strong>
        </div>

        <div className="career-metric">
          <span>Enabled boards</span>
          <strong>{enabledCount} / {sources.length}</strong>
        </div>

        <div className="career-metric">
          <span>Latest successful refresh</span>
          <strong>
            {dateLabel(latestRefresh || null)}
          </strong>
        </div>
      </div>

      {error && (
        <p className="notice error-notice" role="alert">
          {error}
        </p>
      )}

      {notice && (
        <p className="notice discover-notice" role="status">{notice}</p>
      )}

      {progress && (
        <p role="status" className="muted">{progress}</p>
      )}

      {manage && (
        <section className="career-group discover-sources">
          <h3 className="career-group-heading">
            <Building2 size={18}/>
            Employer job boards
          </h3>

          <p className="muted">
            Choose a verified employer or enter a supported
            career board URL. Only configured employers are searched.
          </p>

          <form onSubmit={event => {
            event.preventDefault();

            void perform(async () => {
              const recognized = recognizeBoard(
                board, sourceProvider,
              );

              const created = await createSource({
                provider: recognized.provider,
                board: recognized.board,
                company: company.trim(),
                enabled: true,
              });

              if (!mounted.current) return;

              setBoard("");
              setCompany("");

              await reload();

              if (!mounted.current) return;

              if (fetchOnAdd) {
                await refreshBoards([created], false);
              } else {
                setNotice("Employer board added. Refresh to retrieve jobs.");
              }
            });
          }}>
            <fieldset
              disabled={busy}
              className="career-fields discover-source-fields"
            >
              <label className="career-wide">
                Verified employers
                <select
                  value=""
                  onChange={event => {
                    const employer = EMPLOYERS.find(
                      item => item.company === event.target.value,
                    );

                    if (!employer) return;

                    setCompany(employer.company);
                    setBoard(employer.board);
                    setSourceProvider(employer.provider);
                  }}
                >
                  <option value="">Choose an employer</option>
                  {EMPLOYERS.map(employer => (
                    <option
                      key={employer.company}
                      value={employer.company}
                      disabled={sources.some(source =>
                        source.provider === employer.provider &&
                        source.board === employer.board
                      )}
                    >
                      {employer.company} · {PROVIDERS[employer.provider]}
                      {sources.some(source =>
                        source.provider === employer.provider &&
                        source.board === employer.board
                      ) ? " (already added)" : ""}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Provider
                <select
                  value={sourceProvider}
                  onChange={event => setSourceProvider(
                    event.target.value as Provider,
                  )}
                >
                  {Object.entries(PROVIDERS)
                    .map(([key, value]) => (
                      <option key={key} value={key}>
                        {value}
                      </option>
                    ))}
                </select>
              </label>

              <label>
                Company name
                <input
                  required
                  maxLength={160}
                  value={company}
                  onChange={event => setCompany(event.target.value)}
                />
              </label>

              <label>
                Board identifier or career URL
                <input
                  required
                  maxLength={2000}
                  placeholder="company-name or https://jobs.lever.co/company"
                  value={board}
                  onChange={event => setBoard(event.target.value)}
                />
              </label>

              <label className="career-wide discover-fetch-option">
                <input
                  type="checkbox"
                  checked={fetchOnAdd}
                  onChange={event => setFetchOnAdd(event.target.checked)}
                />
                Fetch public jobs immediately after adding
              </label>

              <div className="career-wide fw-actions">
                <button
                  type="submit"
                  className="secondary-button fw-primary"
                  disabled={
                    sources.length >= 100 ||
                    !company.trim() ||
                    !board.trim()
                  }
                >
                  {fetchOnAdd ? "Add and fetch jobs" : "Add employer board"}
                </button>
              </div>
            </fieldset>
          </form>

          <div className="discover-source-list">
            {sources.map(source => (
              <article
                className="discover-source"
                key={source.id}
              >
                <div>
                  <strong>{source.company}</strong>
                  <p className="muted">
                    {PROVIDERS[source.provider]} · {source.board}
                  </p>
                  <p className="muted">
                    {source.enabled ? "Enabled" : "Disabled"}
                    {" · "}
                    {SOURCE_STATUS[source.last_result]}
                    {" · Last success: "}
                    {dateLabel(source.last_success_at)}
                  </p>
                </div>

                <div className="fw-actions">
                  <button
                    className="secondary-button"
                    disabled={busy || !source.enabled}
                    onClick={() => void perform(
                      () => refreshBoards([source], true),
                    )}
                  >
                    Refresh
                  </button>

                  <button
                    className="secondary-button"
                    disabled={busy}
                    onClick={() => void perform(async () => {
                      await updateSource(source, {
                        provider: source.provider,
                        board: source.board,
                        company: source.company,
                        enabled: !source.enabled,
                      });

                      await reload();
                    })}
                  >
                    {source.enabled ? "Disable" : "Enable"}
                  </button>

                  <button
                    className="secondary-button fw-delete"
                    disabled={busy}
                    onClick={() => {
                      if (!window.confirm(
                        "Remove this employer board and cached listings? Saved applications will remain.",
                      )) return;

                      void perform(async () => {
                        await deleteSource(source);
                        await reload();
                      });
                    }}
                  >
                    Remove
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      <form
        className="discover-search"
        onSubmit={event => {
          event.preventDefault();

          void perform(() =>
            loadJobs(
              search.trim(), provider, 0, location, freshness,
            ),
          );
        }}
      >
        <label>
          Search opportunities
          <input
            value={search}
            maxLength={200}
            placeholder="e.g. Python software engineer"
            onChange={event => setSearch(event.target.value)}
          />
        </label>

        <label>
          Provider
          <select
            value={provider}
            onChange={event => setProvider(
              event.target.value as Provider | "",
            )}
          >
            <option value="">All sources</option>

            {Object.entries(PROVIDERS)
              .map(([key, value]) => (
                <option key={key} value={key}>
                  {value}
                </option>
              ))}
          </select>
        </label>

        <label>
          Location
          <input
            value={location}
            maxLength={200}
            placeholder="City, region or remote"
            onChange={event => setLocation(event.target.value)}
          />
        </label>

        <label>
          Last checked
          <select
            value={freshness}
            onChange={event => setFreshness(
              event.target.value as Freshness,
            )}
          >
            <option value="all">Any time</option>
            <option value="fresh">Within 6 hours</option>
            <option value="stale">Older than 6 hours</option>
          </select>
        </label>

        <button
          type="submit"
          className="secondary-button fw-primary"
          disabled={busy}
        >
          <Search size={16}/>
          Search
        </button>

        <button
          type="button"
          className="secondary-button"
          disabled={busy}
          onClick={() => {
            setSearch("");
            setProvider("");
            setLocation("");
            setFreshness("all");

            void perform(() => loadJobs("", "", 0, "", "all"));
          }}
        >
          Clear filters
        </button>
      </form>

      <div className="discover-toolbar">
        <button
          className="secondary-button"
          disabled={busy || !enabledCount}
          onClick={() => void perform(
            () => refreshBoards(sources, false),
          )}
        >
          <RefreshCw size={16}/>
          Update older results
        </button>

        <button
          className="secondary-button"
          disabled={busy || !enabledCount}
          onClick={() => void perform(
            () => refreshBoards(sources, true),
          )}
        >
          Refresh all
        </button>

        <button
          className="secondary-button"
          disabled={busy}
          onClick={() => void perform(reload)}
        >
          Reload results
        </button>
      </div>

      {!busy && jobs.length === 0 && (
        <div className="career-empty">
          <BriefcaseBusiness size={30}/>
          <h3>
            {enabledCount
              ? "No matching opportunities"
              : "Configure an employer board"}
          </h3>
          <p className="muted">
            {enabledCount
              ? "Refresh your sources or adjust the search."
              : "Add and refresh a public employer board to discover jobs."}
          </p>
        </div>
      )}

      {selected && (
        <section className="career-group discover-detail">
          <div className="discover-heading">
            <div>
              <h3>{selected.title}</h3>
              <p className="muted">{selected.company}</p>
            </div>

            <button
              className="secondary-button"
              onClick={() => setSelected(null)}
            >
              Close details
            </button>
          </div>

          <JobIntelligence
            key={`${selected.id}:${selected.last_seen_at}`}
            job={selected}
            disabled={busy}
          />

          <p className="discover-description">
            {selected.description || "No description supplied."}
          </p>

          <button
            className="secondary-button fw-primary"
            disabled={busy || !!selected.application_id}
            onClick={() => void perform(
              () => saveOpportunity(selected),
            )}
          >
            {selected.application_id
              ? "Saved to Applications"
              : "Save to Applications"}
          </button>
        </section>
      )}

      <div className="discover-results">
        {jobs.map(job => {
          const link = safeJobLink(
            job.apply_url || job.posting_url,
            job.provider,
            job.board,
            job.external_id,
          );

          return (
            <article className="discover-job" key={job.id}>
              <div className="discover-job-heading">
                <div className="discover-job-icon">
                  <Building2 size={24}/>
                </div>

                <div className="discover-job-title">
                  <h3>{job.title}</h3>
                  <p>{job.company}</p>

                  <p className="muted discover-location">
                    <MapPin size={14}/>
                    {job.location || "Location not specified"}
                  </p>
                </div>
              </div>

              <div className="discover-tags">
                <span className="discover-tag">
                  {PROVIDERS[job.provider]}
                </span>

                <span className="discover-tag">
                  {job.work_mode === "unknown"
                    ? "Work arrangement unknown"
                    : job.work_mode}
                </span>

                {job.employment_type && (
                  <span className="discover-tag">
                    {job.employment_type}
                  </span>
                )}

                {job.stale && (
                  <span className="discover-tag discover-stale">
                    Needs refresh
                  </span>
                )}

                {["failed", "limited"].includes(job.last_result) && (
                  <span className="discover-tag discover-stale">
                    Refresh incomplete
                  </span>
                )}

                {job.application_id && (
                  <span className="discover-tag">
                    Saved to Applications
                  </span>
                )}
              </div>

              <p className="muted">
                Last seen: {dateLabel(job.last_seen_at)}
              </p>

              <div className="fw-actions">
                <button
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => void perform(async () => {
                    const detail = await getJob(job.id);

                    if (mounted.current) setSelected(detail);
                  })}
                >
                  View details
                </button>

                <button
                  className="secondary-button"
                  disabled={busy || !!job.application_id}
                  onClick={() => void perform(
                    () => saveOpportunity(job),
                  )}
                >
                  <Bookmark size={16}/>
                  {job.application_id ? "Saved" : "Save job"}
                </button>

                {link && (
                  <a
                    className="secondary-button fw-primary"
                    href={link}
                    target="_blank"
                    rel="noopener noreferrer"
                    referrerPolicy="no-referrer"
                  >
                    View opportunity
                    <ExternalLink size={15}/>
                  </a>
                )}
              </div>
            </article>
          );
        })}
      </div>

      {nextOffset !== null && (
        <button
          className="secondary-button"
          disabled={busy}
          onClick={() => void perform(
            () => loadJobs(
              appliedSearch,
              appliedProvider,
              nextOffset,
            ),
          )}
        >
          Load more opportunities
        </button>
      )}

      <section className="career-group">
        <h3>Search additional job platforms</h3>

        <p className="muted">
          Opens external searches. Aegis does not scrape these
          platforms or submit applications.
        </p>

        <div className="fw-actions">
          <a
            className="secondary-button"
            href={externalSearch("linkedin", search)}
            target="_blank"
            rel="noopener noreferrer"
            referrerPolicy="no-referrer"
          >
            LinkedIn Jobs <ExternalLink size={15}/>
          </a>

          <a
            className="secondary-button"
            href={externalSearch("indeed", search)}
            target="_blank"
            rel="noopener noreferrer"
            referrerPolicy="no-referrer"
          >
            Indeed <ExternalLink size={15}/>
          </a>
        </div>
      </section>
    </section>
  );
}
