"""Local deterministic matching, without external execution.

Scores describe observed compatibility, not hiring
probability or verified candidate qualifications.
"""

import re
import unicodedata

from aegis.schemas.career import CareerProfile
from aegis.schemas.discovery import JobListing
from aegis.schemas.matching import (
    MatchDimension,
    MatchResult,
)


from aegis.services.job_qualifications import (
    extract_qualifications,
    review_items,
)


WEIGHTS = {
    "required_skills": 40,
    "preferred_skills": 15,
    "target_role": 20,
    "location": 10,
    "work_mode": 10,
    "employment_type": 5,
}

MIN_EVALUATED_WEIGHT = 20
MIN_EVIDENCE_COVERAGE = 50

EMPLOYMENT_TYPES = {
    "full time": "full_time",
    "fulltime": "full_time",
    "part time": "part_time",
    "parttime": "part_time",
    "contract": "contract",
    "contractor": "contract",
    "intern": "internship",
    "internship": "internship",
}


def normalize(value):
    value = unicodedata.normalize(
        "NFKC", value,
    ).casefold()

    return " ".join(
        re.sub(r"[_\-\u2010-\u2015]", " ", value).split()
    )


def contains_phrase(text, phrase):
    return contains_normalized_phrase(
        normalize(text), normalize(phrase),
    )


def contains_normalized_phrase(text, phrase):

    if not phrase:
        return False

    pattern = (
        r"(?<![\w+#.])"
        + re.escape(phrase)
        + r"(?![\w+#]|\.\w)"
    )

    return re.search(pattern, text) is not None


def dimension(name, status, explanation, value=None):
    return MatchDimension(
        name=name,
        weight=WEIGHTS[name],
        status=status,
        explanation=explanation,
        value=value,
    )


def phrase_preference(name, preferences, observed):
    preferences = [
        item for item in preferences
        if normalize(item)
    ]

    if not preferences:
        return dimension(
            name, "not_applicable",
            "No preference configured.",
        )

    if not normalize(observed):
        return dimension(
            name, "unknown",
            "The listing does not provide this information.",
        )

    if any(
        contains_phrase(observed, item)
        for item in preferences
    ):
        return dimension(
            name, "matched",
            "Listing text matches a configured preference.",
            100,
        )

    # Text mismatch is not proof of incompatibility.
    # Synonyms and geographic equivalence are not inferred.
    return dimension(
        name, "unknown",
        "No exact preference match found; review manually.",
    )


def explicit_preference(name, preferred, observed):
    if preferred == "any":
        return dimension(
            name, "not_applicable",
            "No restriction configured.",
        )

    if observed in {None, "", "unknown"}:
        return dimension(
            name, "unknown",
            "The listing does not provide this information.",
        )

    if preferred == observed:
        return dimension(
            name, "matched",
            "Matches the configured preference.",
            100,
        )

    return dimension(
        name, "mismatch",
        "Listing metadata differs from the configured preference.",
        0,
    )


def summarize(dimensions):
    names = [item.name for item in dimensions]

    if len(names) != len(WEIGHTS) or set(names) != set(WEIGHTS):
        raise ValueError("Invalid scoring dimensions")

    if any(
        item.weight != WEIGHTS[item.name]
        for item in dimensions
    ):
        raise ValueError("Invalid scoring weights")

    applicable = sum(
        item.weight for item in dimensions
        if item.status != "not_applicable"
    )

    evaluated = [
        item for item in dimensions
        if item.value is not None
    ]

    evaluated_weight = sum(
        item.weight for item in evaluated
    )

    coverage = (
        round(100 * evaluated_weight / applicable)
        if applicable else 0
    )

    score = None

    if (
        evaluated_weight >= MIN_EVALUATED_WEIGHT
        and coverage >= MIN_EVIDENCE_COVERAGE
    ):
        score = round(
            sum(
                item.weight * item.value
                for item in evaluated
            ) / evaluated_weight
        )

    return MatchResult(
        score=score,
        evidence_coverage=coverage,
        evaluated_weight=evaluated_weight,
        applicable_weight=applicable,
        dimensions=dimensions,
        limitations=[
            "Compatibility is not a hiring probability.",
            "A score requires at least 50 percent evidence coverage.",
            "Missing evidence does not establish a missing qualification.",
            "Salary and work authorization are not evaluated.",
            "Qualification extraction uses a limited vocabulary.",
            "Resume mentions are not verified skills.",
            "Unidentified requirements may still apply.",
            "Skill scores measure declared evidence coverage.",
            "Preferences use literal text and explicit listing metadata.",
        ],
    )


def qualification_dimension(name, importance, evidence):
    relevant = [
        item for item in evidence
        if item.importance == importance
    ]

    if not relevant:
        return dimension(
            name, "unknown",
            "No unambiguous skills identified in this category.",
        )

    declared = sum(
        item.status == "profile_match"
        for item in relevant
    )

    # Resume mentions are shown as evidence, but are not
    # treated as confirmed qualifications.
    if not declared:
        return dimension(
            name, "unknown",
            "No identified skills are explicitly declared in the profile.",
        )

    return dimension(
        name,
        "matched",
        f"{declared} of {len(relevant)} identified skills "
        "are explicitly declared in the profile.",
        round(100 * declared / len(relevant)),
    )


def match_job(
    profile: CareerProfile,
    job: JobListing,
    resume_text: str = "",
):
    profile = CareerProfile.model_validate(
        profile.model_dump()
    )

    job = JobListing.model_validate(
        job.model_dump()
    )

    employment = EMPLOYMENT_TYPES.get(
        normalize(job.employment_type),
    )

    evidence = extract_qualifications(
        profile,
        job.description,
        resume_text,
        normalize,
        contains_normalized_phrase,
    )

    dimensions = [
        qualification_dimension(
            "required_skills", "required", evidence,
        ),
        qualification_dimension(
            "preferred_skills", "preferred", evidence,
        ),
        phrase_preference(
            "target_role",
            profile.target_roles,
            job.title,
        ),
        phrase_preference(
            "location",
            profile.target_locations,
            job.location,
        ),
        explicit_preference(
            "work_mode",
            profile.work_mode,
            job.work_mode,
        ),
        explicit_preference(
            "employment_type",
            profile.employment_type,
            employment,
        ),
    ]

    result = summarize(dimensions)

    return result.model_copy(update={
        "qualifications": evidence,
        "review_items": review_items(job.description),
    })
