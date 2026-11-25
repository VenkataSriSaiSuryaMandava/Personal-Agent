"""Local company and listing intelligence.

Provider provenance is not independent employer verification.
Warning indicators are not fraud determinations.
"""

import re
import time

from aegis.schemas.discovery import CACHE_TTL
from aegis.services.job_adapters import safe_link
from aegis.storage.database import DATABASE_PATH, connect
from aegis.storage.discovery import SourceNotFound


WARNING_RULES = (
    (
        "advance_payment",
        r"\b(?:upfront fee|advance payment|"
        r"application fee|registration fee|"
        r"pay for training|pay for equipment)\b",
        "Review any request for applicant payments.",
    ),
    (
        "financial_transfer",
        r"\b(?:wire transfer|gift cards?|"
        r"deposit a check|deposit a cheque|"
        r"send cryptocurrency)\b",
        "Review financial transfer language carefully.",
    ),
    (
        "sensitive_information",
        r"\b(?:bank account details|"
        r"online banking password|"
        r"social security number|"
        r"passport number)\b",
        "Verify the purpose and recipient before sharing sensitive information.",
    ),
    (
        "unusual_recruitment",
        r"\b(?:telegram interview|"
        r"interview via telegram|"
        r"whatsapp interview|"
        r"interview via whatsapp|"
        r"job offer without interview)\b",
        "Independently verify the recruitment process.",
    ),
)


def listing_indicators(job):
    description = job.get("description", "")

    if (
        not isinstance(description, str)
        or len(description) > 30000
    ):
        raise ValueError("Invalid listing description")

    warnings = []

    if not description.strip():
        warnings.append({
            "code": "missing_description",
            "severity": "information",
            "message":
                "The cached listing has no job description.",
        })

    if job.get("stale"):
        warnings.append({
            "code": "stale_listing",
            "severity": "information",
            "message":
                "Refresh the source before relying on this listing.",
        })

    for field in ("posting_url", "apply_url"):
        value = job.get(field, "")

        if field == "apply_url" and not value:
            continue

        if not safe_link(
            value,
            job["provider"],
            job["board"],
            job["external_id"],
        ):
            warnings.append({
                "code": "unsafe_" + field,
                "severity": "warning",
                "message":
                    "The link did not pass provider URL validation.",
            })

    for code, pattern, message in WARNING_RULES:
        match = re.search(
            pattern, description, re.I,
        )

        if match:
            warnings.append({
                "code": code,
                "severity": "review",
                "message": message,
                "matched_phrase": match.group(0),
            })

    return {
        "indicators": warnings,
        "assessment": (
            "review_recommended"
            if warnings else "no_indicators_detected"
        ),
        "disclaimer":
            "These limited text and source checks do not "
            "establish whether a listing is legitimate or fraudulent.",
    }


def get_company_intelligence(
    user_id,
    source_id,
    path=DATABASE_PATH,
):
    now = int(time.time())

    with connect(path) as c:
        c.execute("BEGIN")

        source = c.execute("""
            SELECT
                id, company, provider, board,
                last_success_at, last_attempt_at,
                last_result
            FROM job_sources
            WHERE user_id = ?
                AND id = ?
                AND enabled = 1
        """, (user_id, source_id)).fetchone()

        if source is None:
            raise SourceNotFound()

        count = c.execute("""
            SELECT COUNT(*)
            FROM job_listings
            WHERE user_id = ?
                AND source_id = ?
                AND is_open = 1
        """, (user_id, source_id)).fetchone()[0]

        modes = c.execute("""
            SELECT work_mode, COUNT(*) AS count
            FROM job_listings
            WHERE user_id = ?
                AND source_id = ?
                AND is_open = 1
            GROUP BY work_mode
        """, (user_id, source_id)).fetchall()

        departments = c.execute("""
            SELECT department, COUNT(*) AS count
            FROM job_listings
            WHERE user_id = ?
                AND source_id = ?
                AND is_open = 1
            GROUP BY department
            ORDER BY count DESC, department
            LIMIT 10
        """, (user_id, source_id)).fetchall()

    distribution = {
        "remote": 0,
        "hybrid": 0,
        "onsite": 0,
        "unknown": 0,
    }

    for row in modes:
        distribution[row["work_mode"]] = row["count"]

    refreshed_at = source["last_success_at"]

    stale = (
        refreshed_at is None
        or not 0 <= now - refreshed_at < CACHE_TTL
    )

    return {
        "source_id": source["id"],
        "company": source["company"],
        "provider": source["provider"],
        "board": source["board"],
        "identity_verified": False,
        "provenance": "configured_public_job_board",
        "open_listings": count,
        "workplace_distribution": distribution,
        "top_departments": [
            {
                "department":
                    row["department"] or "Not specified",
                "count": row["count"],
            }
            for row in departments
        ],
        "other_department_listings": count - sum(
            row["count"] for row in departments
        ),
        "last_success_at": refreshed_at,
        "last_attempt_at": source["last_attempt_at"],
        "last_result": source["last_result"],
        "stale": stale,
        "unverified_fields": [
            "Employer identity",
            "Company size",
            "Financial stability",
            "Employee reviews",
            "Hiring growth",
            "Sponsorship history",
        ],
        "limitations": [
            "Counts describe cached listings, not total company vacancies.",
            "Company name is the configured source label.",
            "Department counts use provider-supplied labels.",
            "No independent company research was performed.",
        ],
    }
