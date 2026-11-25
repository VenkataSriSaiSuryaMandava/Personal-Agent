import type { Provider } from "./discovery";

export type MatchDimension = {
  name:
    "required_skills" | "preferred_skills" |
    "target_role" | "location" |
    "work_mode" | "employment_type";
  weight: number;
  status:
    "matched" | "mismatch" |
    "unknown" | "not_applicable";
  value: number | null;
  explanation: string;
};

export type QualificationEvidence = {
  skill: string;
  importance: "required" | "preferred" | "unspecified";
  status:
    "profile_match" | "resume_mention" | "not_evidenced";
  listing_evidence: string;
};

export type JobIntelligenceResult = {
  job_id: string;
  profile_revision: number;

  resume: {
    id: string;
    title: string;
    revision: number;
    has_text: boolean;
  } | null;

  matching: {
    algorithm_version: string;
    score: number | null;
    evidence_coverage: number;
    evaluated_weight: number;
    applicable_weight: number;
    dimensions: MatchDimension[];
    qualifications: QualificationEvidence[];
    review_items: string[];
    limitations: string[];
  };

  company: {
    source_id: string;
    company: string;
    provider: Provider;
    board: string;
    identity_verified: boolean;
    provenance: string;
    open_listings: number;
    workplace_distribution: Record<
      "remote" | "hybrid" | "onsite" | "unknown",
      number
    >;
    top_departments: {
      department: string;
      count: number;
    }[];
    other_department_listings: number;
    last_success_at: number | null;
    last_attempt_at: number | null;
    last_result: string;
    stale: boolean;
    unverified_fields: string[];
    limitations: string[];
  };

  listing_review: {
    indicators: {
      code: string;
      severity: "information" | "review" | "warning";
      message: string;
      matched_phrase?: string;
    }[];
    assessment:
      "review_recommended" | "no_indicators_detected";
    disclaimer: string;
  };

  listing_last_seen_at: number;
  listing_stale: boolean;
};
