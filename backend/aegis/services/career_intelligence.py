"""Owner-scoped, read-only career intelligence."""

from aegis.schemas.career import CareerProfile
from aegis.schemas.discovery import JobListing
from aegis.services.job_matching import match_job
from aegis.services.company_intelligence import (
    get_company_intelligence,
    listing_indicators,
)
from aegis.storage import career, discovery
from aegis.storage.database import DATABASE_PATH, connect


def analyze_job(
    user_id,
    identifier,
    path=DATABASE_PATH,
):
    job = discovery.get_job(
        user_id, identifier, path,
    )

    snapshot = career.get_profile(
        user_id, path,
    )

    profile = CareerProfile.model_validate(
        snapshot["profile"]
    )

    with connect(path) as c:
        resume = c.execute("""
            SELECT id, title, revision, extracted_text
            FROM resume_versions
            WHERE user_id = ?
                AND is_active = 1
        """, (user_id,)).fetchone()

    listing = JobListing.model_validate({
        name: job[name]
        for name in JobListing.model_fields
    })

    result = match_job(
        profile,
        listing,
        resume_text=(
            resume["extracted_text"] if resume else ""
        ),
    )

    company = get_company_intelligence(
        user_id,
        job["source_id"],
        path,
    )

    return {
        "job_id": identifier,
        "profile_revision": snapshot["revision"],
        "resume": (
            {
                "id": resume["id"],
                "title": resume["title"],
                "revision": resume["revision"],
                "has_text": bool(
                    resume["extracted_text"].strip()
                ),
            }
            if resume else None
        ),
        "matching": result.model_dump(),
        "company": company,
        "listing_review": listing_indicators(job),
        "listing_last_seen_at": job["last_seen_at"],
        "listing_stale": job["stale"],
    }
