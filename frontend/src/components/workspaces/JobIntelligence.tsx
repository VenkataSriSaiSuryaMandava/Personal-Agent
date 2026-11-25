"use client";

import { useEffect, useRef, useState } from "react";

import {
  getJobIntelligence,
  type JobDetail,
} from "@/lib/discovery";

import type {
  JobIntelligenceResult,
  MatchDimension,
  QualificationEvidence,
} from "@/lib/matching";

import "./JobIntelligence.css";

const DIMENSIONS: Record<MatchDimension["name"], string> = {
  required_skills: "Required skills",
  preferred_skills: "Preferred skills",
  target_role: "Target role",
  location: "Location",
  work_mode: "Work arrangement",
  employment_type: "Employment type",
};

const STATUSES: Record<MatchDimension["status"], string> = {
  matched: "Evidence found",
  mismatch: "Preference differs",
  unknown: "Unknown",
  not_applicable: "Not configured",
};

const EVIDENCE: Record<QualificationEvidence["status"], string> = {
  profile_match: "Declared in profile",
  resume_mention: "Mentioned in resume",
  not_evidenced: "Not demonstrated",
};

function dateLabel(value: number | null) {
  return value === null
    ? "Never"
    : new Date(value * 1000).toLocaleString();
}

export default function JobIntelligence({
  job,
  disabled,
}: {
  job: JobDetail;
  disabled: boolean;
}) {
  const [result, setResult] =
    useState<JobIntelligenceResult | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const mounted = useRef(false);
  const operation = useRef(false);

  useEffect(() => {
    mounted.current = true;

    return () => {
      mounted.current = false;
    };
  }, []);

  async function analyze() {
    if (disabled || operation.current) return;

    operation.current = true;

    setBusy(true);
    setError("");
    setResult(null);

    try {
      const data = await getJobIntelligence(job.id);

      if (data.job_id !== job.id) {
        throw new Error("Unexpected matching response.");
      }

      if (mounted.current) setResult(data);

    } catch (failure) {
      if (mounted.current) {
        setError(
          failure instanceof Error
            ? failure.message
            : "Matching unavailable.",
        );
      }

    } finally {
      operation.current = false;

      if (mounted.current) setBusy(false);
    }
  }

  const research = new URL("https://www.google.com/search");

  research.searchParams.set(
    "q", `${job.company} official company careers`,
  );

  return (
    <section className="ji-panel">
      <div className="ji-heading">
        <div>
          <h3>Match &amp; Intelligence</h3>
          <p className="muted">
            Local analysis using your saved profile and active resume.
          </p>
        </div>

        <button
          type="button"
          className="secondary-button"
          disabled={disabled || busy}
          onClick={() => void analyze()}
        >
          {busy
            ? "Analyzing..."
            : result
              ? "Recalculate match"
              : "Analyze match"}
        </button>
      </div>

      {busy && (
        <p role="status" className="muted">
          Comparing locally stored qualifications and preferences.
        </p>
      )}

      {error && <p role="alert">{error}</p>}

      {result && (
        <>
          <div className="ji-metrics">
            <div className="ji-metric">
              <span>Compatibility</span>
              <strong>
                {result.matching.score === null
                  ? "More evidence needed"
                  : `${result.matching.score}/100`}
              </strong>
            </div>

            <div className="ji-metric">
              <span>Evidence coverage</span>
              <strong>{result.matching.evidence_coverage}%</strong>
            </div>

            <div className="ji-metric">
              <span>Cached company listings</span>
              <strong>{result.company.open_listings}</strong>
            </div>
          </div>

          <p className="muted">
            Compatibility is not a hiring probability.
            A score requires at least 50% evidence coverage.
            Unknown information is not a confirmed mismatch.
          </p>

          <p className="muted">
            {result.profile_revision
              ? `Saved profile revision ${result.profile_revision}`
              : "No saved career profile"}
            {" · "}
            {result.resume
              ? `${result.resume.title} (revision ${result.resume.revision})`
              : "No active resume"}
          </p>

          {result.resume && !result.resume.has_text && (
            <p className="muted">
              The active resume has no extracted text.
            </p>
          )}

          {result.listing_stale && (
            <p className="muted">
              Listing data is stale. Refresh the employer board
              before relying on the analysis.
            </p>
          )}

          <details className="ji-details" open>
            <summary>Compatibility breakdown</summary>

            {result.matching.dimensions.map(item => (
              <div className="ji-row" key={item.name}>
                <div>
                  <strong>{DIMENSIONS[item.name]}</strong>
                  <p className="muted">{item.explanation}</p>
                </div>

                <span className="discover-tag">
                  {item.value === null
                    ? STATUSES[item.status]
                    : `${item.value}%`}
                </span>
              </div>
            ))}
          </details>

          <div className="ji-group">
            <h4>Qualification evidence</h4>

            {!result.matching.qualifications.length && (
              <p className="muted">
                No recognized skills identified.
                Review the original requirements manually.
              </p>
            )}

            {(
              ["required", "preferred", "unspecified"] as const
            ).map(importance => {
              const items = result.matching.qualifications.filter(
                item => item.importance === importance,
              );

              if (!items.length) return null;

              return (
                <details
                  key={importance}
                  open={importance === "required"}
                  className="ji-details"
                >
                  <summary>
                    {importance === "unspecified"
                      ? "Other skill mentions"
                      : `${importance[0].toUpperCase()}${importance.slice(1)} skills`}
                    {" · "}{items.length}
                  </summary>

                  {items.map(item => (
                    <div className="ji-evidence" key={item.skill}>
                      <div className="ji-row">
                        <strong>{item.skill}</strong>

                        <span className="discover-tag">
                          {EVIDENCE[item.status]}
                        </span>
                      </div>

                      <p className="muted">
                        Listing evidence: {item.listing_evidence}
                      </p>
                    </div>
                  ))}
                </details>
              );
            })}
          </div>

          {!!result.matching.review_items.length && (
            <details className="ji-details">
              <summary>Requirements to verify</summary>

              <ul>
                {result.matching.review_items.map(item => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </details>
          )}

          <details className="ji-details">
            <summary>Company intelligence</summary>

            <p>
              <strong>{result.company.company}</strong>
              {" · "}{result.company.provider}
              {" / "}{result.company.board}
            </p>

            <p className="muted">
              Configured employer board.
              Employer identity is not independently verified.
            </p>

            <p className="muted">
              Last refreshed: {dateLabel(result.company.last_success_at)}
              {" · "}{result.company.stale ? "Stale" : "Current"}
              {" · "}Last result: {result.company.last_result}
            </p>

            <div className="ji-metrics">
              {Object.entries(
                result.company.workplace_distribution,
              ).map(([mode, count]) => (
                <div className="ji-metric" key={mode}>
                  <span>{mode}</span>
                  <strong>{count}</strong>
                </div>
              ))}
            </div>

            {!!result.company.top_departments.length && (
              <div className="ji-group">
                <h4>Departments</h4>

                {result.company.top_departments.map((item, index) => (
                  <div className="ji-row" key={index}>
                    <span>{item.department}</span>
                    <strong>{item.count}</strong>
                  </div>
                ))}

                {!!result.company.other_department_listings && (
                  <p>
                    Other department listings:
                    {" "}{result.company.other_department_listings}
                  </p>
                )}
              </div>
            )}

            <p className="muted">
              Not independently verified:
              {" "}{result.company.unverified_fields.join(", ")}.
            </p>

            <a
              className="secondary-button"
              href={research.href}
              target="_blank"
              rel="noopener noreferrer"
              referrerPolicy="no-referrer"
            >
              Research company
            </a>

            <p className="muted">
              Opening this link sends the configured employer name
              and generic research terms to Google.
            </p>
          </details>

          <details
            className="ji-details"
            open={result.listing_review.indicators.length > 0}
          >
            <summary>Listing review</summary>

            {result.listing_review.indicators.length ? (
              result.listing_review.indicators.map(item => (
                <div className="ji-warning" key={item.code}>
                  <strong>
                    {item.severity === "information"
                      ? "Information"
                      : "Review recommended"}
                  </strong>

                  <p>{item.message}</p>

                  {item.matched_phrase && (
                    <p className="muted">
                      Matched wording: {item.matched_phrase}
                    </p>
                  )}
                </div>
              ))
            ) : (
              <p>No indicators detected by these limited checks.</p>
            )}

            <p className="muted">
              {result.listing_review.disclaimer}
            </p>
          </details>

          <details className="ji-details">
            <summary>Methodology and limitations</summary>

            <ul>
              {[
                ...result.matching.limitations,
                ...result.company.limitations,
              ].map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>

            <p className="muted">
              Algorithm version {result.matching.algorithm_version}.
              Recalculate after editing your saved profile or resume.
            </p>
          </details>
        </>
      )}
    </section>
  );
}
