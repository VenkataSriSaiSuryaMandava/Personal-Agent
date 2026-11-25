import pytest

from aegis.schemas.career import CareerProfile
from aegis.schemas.discovery import JobListing
from aegis.services.job_matching import match_job


def listing(description):
    return JobListing(
        external_id="synthetic",
        title="Software Engineer",
        description=description,
        posting_url=(
            "https://jobs.lever.co/synthetic/synthetic"
        ),
    )


def evidence(result):
    return {
        item.skill: item
        for item in result.qualifications
    }


def dimensions(result):
    return {
        item.name: item
        for item in result.dimensions
    }


def test_required_and_preferred_sections():
    result = match_job(
        CareerProfile(skills=["Python", "Docker"]),
        listing(
            "Required qualifications\n"
            "Python\nSQL\n"
            "Preferred qualifications\n"
            "Docker\nKubernetes"
        ),
    )

    items = evidence(result)

    assert items["Python"].importance == "required"
    assert items["SQL"].importance == "required"
    assert items["Docker"].importance == "preferred"
    assert items["Kubernetes"].importance == "preferred"

    assert items["Python"].status == "profile_match"
    assert items["SQL"].status == "not_evidenced"

    assert dimensions(result)["required_skills"].value == 50
    assert dimensions(result)["preferred_skills"].value == 50


def test_resume_mention_is_not_confirmed_skill():
    result = match_job(
        CareerProfile(),
        listing("Required skills\nPython"),
        resume_text="Experience with Python.",
    )

    assert evidence(result)["Python"].status == "resume_mention"
    assert dimensions(result)["required_skills"].status == "unknown"
    assert result.score is None


def test_missing_evidence_is_not_explicit_mismatch():
    result = match_job(
        CareerProfile(skills=["Java"]),
        listing("Required skills\nPython"),
    )

    assert evidence(result)["Python"].status == "not_evidenced"
    assert dimensions(result)["required_skills"].status == "unknown"


def test_custom_profile_skill():
    result = match_job(
        CareerProfile(skills=["Synthetic Framework"]),
        listing(
            "Required skills\nSynthetic Framework"
        ),
    )

    item = evidence(result)["Synthetic Framework"]

    assert item.status == "profile_match"
    assert item.importance == "required"


@pytest.mark.parametrize("description", [
    "Required skills\nPython or Java",
    "Required skills\nPython/Java",
    "Required skills\nPython not required",
    "Required skills\nNo experience with Python necessary",
])
def test_ambiguous_requirements_not_mandatory(description):
    result = match_job(
        CareerProfile(skills=["Python"]),
        listing(description),
    )

    assert evidence(result)["Python"].importance == "unspecified"
    assert dimensions(result)["required_skills"].value is None


def test_optional_override():
    result = match_job(
        CareerProfile(skills=["Python"]),
        listing("Required qualifications\nPython preferred"),
    )

    assert evidence(result)["Python"].importance == "preferred"


def test_section_boundary():
    result = match_job(
        CareerProfile(skills=["Python"]),
        listing(
            "Required qualifications\nPython\n"
            "Responsibilities\nDocker"
        ),
    )

    assert evidence(result)["Docker"].importance == "unspecified"


def test_duplicate_skills_not_double_counted():
    result = match_job(
        CareerProfile(skills=["Python", "python"]),
        listing(
            "Required skills\nPython\npython\nPYTHON"
        ),
    )

    assert len(result.qualifications) == 1
    assert dimensions(result)["required_skills"].value == 100


def test_substring_collision():
    result = match_job(
        CareerProfile(skills=["Java"]),
        listing("Required skills\nJavaScript"),
    )

    assert "Java" not in evidence(result)
    assert evidence(result)["JavaScript"].status == "not_evidenced"


def test_review_items_do_not_assert_eligibility():
    result = match_job(
        CareerProfile(sponsorship_required="yes"),
        listing(
            "5 years of experience\n"
            "Bachelor degree\n"
            "Visa sponsorship\n"
            "Security clearance"
        ),
    )

    assert len(result.review_items) == 4
    assert result.score is None


def test_private_resume_text_not_echoed():
    result = match_job(
        CareerProfile(),
        listing("Required skills\nPython"),
        resume_text=(
            "Python\n"
            "Synthetic private contact information"
        ),
    )

    assert "Synthetic private contact information" not in (
        result.model_dump_json()
    )


def test_oversized_resume_rejected():
    with pytest.raises(ValueError):
        match_job(
            CareerProfile(),
            listing("Python"),
            resume_text="x" * 100001,
        )


def test_deterministic_evidence():
    profile = CareerProfile(skills=["Python"])

    job = listing("Required skills\nPython\nSQL")

    assert match_job(profile, job) == match_job(profile, job)


def test_ambiguous_skill_cannot_become_mandatory():
    result = match_job(
        CareerProfile(skills=["Python"]),
        listing(
            "Required skills\n"
            "Python\n"
            "Python or Java"
        ),
    )

    assert evidence(result)["Python"].importance == "unspecified"


def test_low_coverage_score_suppressed():
    result = match_job(
        CareerProfile(
            target_roles=["Software Engineer"],
        ),
        listing("Python development"),
    )

    assert result.evaluated_weight == 20
    assert result.evidence_coverage < 50
    assert result.score is None


def test_sufficient_evidence_allows_score():
    result = match_job(
        CareerProfile(skills=["Python", "SQL"]),
        listing("Required skills\nPython\nSQL"),
    )

    assert result.evaluated_weight == 40
    assert result.evidence_coverage >= 50
    assert result.score == 100


@pytest.mark.parametrize("description", [
    "Required skills\nPython not mandatory",
    "Required skills\nPython not needed",
    "Required skills\nNo prior Python experience",
])
def test_additional_ambiguous_wording(description):
    result = match_job(
        CareerProfile(skills=["Python"]),
        listing(description),
    )

    assert evidence(result)["Python"].importance == "unspecified"
