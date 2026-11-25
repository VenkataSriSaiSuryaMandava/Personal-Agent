import json

import pytest

from aegis.schemas.discovery import (
    JobSourceInput,
    MAX_RESPONSE_BYTES,
    MAX_LISTINGS_PER_SOURCE,
)

from aegis.services.job_adapters import (
    normalize_response,
    safe_link,
    html_to_text,
    SourceResponseRejected,
)


def source(provider):
    return JobSourceInput(
        provider=provider,
        board="synthetic",
        company="Synthetic Company",
    )


GREENHOUSE = {
    "id": 12345,
    "title": "Software Engineer",
    "location": {"name": "San Francisco"},
    "departments": [{"name": "Engineering"}],
    "absolute_url":
        "https://job-boards.greenhouse.io/synthetic/jobs/12345",
    "content": "<p>Python and SQL</p>",
}


LEVER = {
    "id": "synthetic-lever-id",
    "text": "Data Engineer",
    "categories": {
        "location": "Remote",
        "team": "Data",
        "commitment": "Full-time",
    },
    "descriptionPlain": "Python and data pipelines",
    "lists": [
        {
            "text": "Requirements",
            "content": "<li>SQL</li>",
        },
    ],
    "workplaceType": "remote",
    "hostedUrl":
        "https://jobs.lever.co/synthetic/synthetic-id",
    "applyUrl":
        "https://jobs.lever.co/synthetic/synthetic-id/apply",
    "createdAt": 1700000000000,
}


ASHBY = {
    "title": "Full Stack Engineer",
    "location": "Seattle",
    "department": "Engineering",
    "descriptionPlain": "React and Python",
    "employmentType": "FullTime",
    "workplaceType": "Hybrid",
    "jobUrl":
        "https://jobs.ashbyhq.com/synthetic/synthetic-id",
    "applyUrl":
        "https://jobs.ashbyhq.com/synthetic/synthetic-id/application",
    "publishedAt": "2026-01-01T00:00:00Z",
    "isListed": True,
}


def parse(provider, payload):
    return normalize_response(
        source(provider),
        json.dumps(payload).encode(),
    )


def test_greenhouse():
    records = parse(
        "greenhouse", {"jobs": [GREENHOUSE]}
    )

    assert len(records) == 1
    job = records[0]

    assert job.external_id == "12345"
    assert job.title == "Software Engineer"
    assert job.department == "Engineering"
    assert job.location == "San Francisco"
    assert job.description == "Python and SQL"
    assert job.work_mode == "unknown"


def test_lever():
    job = parse("lever", [LEVER])[0]

    assert job.title == "Data Engineer"
    assert job.work_mode == "remote"
    assert job.published_at == 1700000000
    assert "SQL" in job.description
    assert "Requirements" in job.description


def test_ashby():
    job = parse(
        "ashby", {"jobs": [ASHBY]}
    )[0]

    assert job.external_id == "synthetic-id"
    assert job.title == "Full Stack Engineer"
    assert job.work_mode == "hybrid"
    assert job.published_at is not None


def test_ashby_unlisted_excluded():
    assert parse(
        "ashby",
        {"jobs": [{**ASHBY, "isListed": False}]},
    ) == []


def test_exact_duplicates_removed():
    assert len(parse(
        "greenhouse",
        {"jobs": [GREENHOUSE, GREENHOUSE]},
    )) == 1


def test_conflicting_duplicate_rejected():
    with pytest.raises(SourceResponseRejected):
        parse(
            "greenhouse",
            {"jobs": [
                GREENHOUSE,
                {**GREENHOUSE, "title": "Different title"},
            ]},
        )


@pytest.mark.parametrize("url", [
    "http://jobs.lever.co/example/job",
    "javascript:alert(1)",
    "data:text/html,test",
    "https://127.0.0.1/test",
    "https://169.254.169.254/test",
    "https://jobs.lever.co.example.invalid/test",
    "https://jobs.lever.co@evil.invalid/test",
    "https://evil.invalid@jobs.lever.co/test",
    "https://jobs.lever.co:444/test",
    "https://jobs.lever.co\\@evil.invalid/test",
    "https://jobs.lever.co//evil.invalid/test",
    "https://jobs.lever.co/test\n",
    "//jobs.lever.co/test",
])
def test_unsafe_url_rejected(url):
    assert safe_link(url, "lever") == ""


def test_html_converted_to_text():
    result = html_to_text(
        "<p>Python</p>"
        "<script>malicious()</script>"
        "<style>hidden content</style>"
        "<iframe>private</iframe>"
        "<p>SQL &amp; React</p>"
    )

    assert "Python" in result
    assert "SQL & React" in result
    assert "malicious()" not in result
    assert "hidden content" not in result
    assert "private" not in result


def test_invalid_posting_url_rejects_snapshot():
    with pytest.raises(SourceResponseRejected):
        parse(
            "lever",
            [{
                **LEVER,
                "hostedUrl": "javascript:alert(1)",
            }],
        )


@pytest.mark.parametrize("raw", [
    b"",
    b"not JSON",
    b'{"jobs":null}',
    b'{"jobs":{} }',
    b'{"jobs":[],"jobs":[]}',
    b'{"jobs":[NaN]}',
    b'{"jobs":[null]}',
    b'{"jobs":[{}]}',
    b"\xff",
])
def test_invalid_response_rejected(raw):
    with pytest.raises(SourceResponseRejected):
        normalize_response(
            source("greenhouse"), raw,
        )


def test_oversized_response_rejected():
    with pytest.raises(SourceResponseRejected):
        normalize_response(
            source("greenhouse"),
            b"x" * (MAX_RESPONSE_BYTES + 1),
        )


def test_listing_limit():
    with pytest.raises(SourceResponseRejected):
        parse(
            "greenhouse",
            {"jobs": [
                {**GREENHOUSE, "id": index}
                for index in range(MAX_LISTINGS_PER_SOURCE + 1)
            ]},
        )


def test_unknown_work_arrangement():
    job = parse(
        "lever",
        [{**LEVER, "workplaceType": "unspecified"}],
    )[0]

    assert job.work_mode == "unknown"


@pytest.mark.parametrize("provider,payload", [
    ("greenhouse", {"jobs": []}),
    ("lever", []),
    ("ashby", {"jobs": []}),
])
def test_empty_board_is_valid(provider, payload):
    assert parse(provider, payload) == []


def test_description_limit():
    job = parse(
        "lever",
        [{
            **LEVER,
            "descriptionPlain": "a" * 40000,
        }],
    )[0]

    assert len(job.description) == 30000


def test_large_employer_listing_limit():
    jobs = [
        {**GREENHOUSE, "id": index}
        for index in range(1000)
    ]

    assert MAX_LISTINGS_PER_SOURCE == 1000
    assert len(parse("greenhouse", {
        "jobs": jobs,
        "meta": {"total": 1000},
    })) == 1000


def test_stripe_board_normalization():
    config = JobSourceInput(
        provider="greenhouse",
        board="stripe",
        company="Stripe",
    )

    row = {
        **GREENHOUSE,
        "absolute_url": (
            "https://stripe.com/careers/listing/"
            "software-engineer/12345?gh_src=example"
        ),
    }

    jobs = normalize_response(config, json.dumps({
        "jobs": [row],
        "meta": {"total": 1},
    }).encode())

    assert jobs[0].posting_url == (
        "https://stripe.com/careers/listing/"
        "software-engineer/12345"
    )


@pytest.mark.parametrize("url,provider,board,external_id", [
    (
        "https://stripe.com/careers/listing/engineer/12345",
        "greenhouse", "other-company", "12345",
    ),
    (
        "https://stripe.com/careers/listing/engineer/12345",
        "lever", "stripe", "12345",
    ),
    (
        "https://stripe.com/careers/listing/engineer/12345",
        "greenhouse", "stripe", "99999",
    ),
    (
        "https://stripe.com.example.invalid/careers/listing/engineer/12345",
        "greenhouse", "stripe", "12345",
    ),
    (
        "https://stripe.com:443/careers/listing/engineer/12345",
        "greenhouse", "stripe", "12345",
    ),
    (
        "https://stripe.com/redirect/12345",
        "greenhouse", "stripe", "12345",
    ),
    (
        "https://stripe.com/careers/listing/engineer/12345#fragment",
        "greenhouse", "stripe", "12345",
    ),
])
def test_stripe_link_scope(url, provider, board, external_id):
    assert safe_link(
        url, provider, board, external_id,
    ) == ""


def test_stripe_search_url_normalization():
    config = JobSourceInput(
        provider="greenhouse",
        board="stripe",
        company="Stripe",
    )

    rows = [
        {
            **GREENHOUSE,
            "id": index,
            "absolute_url": (
                "https://stripe.com/jobs/search?"
                f"gh_jid={index}"
            ),
        }
        for index in range(1, 772)
    ]

    jobs = normalize_response(config, json.dumps({
        "jobs": rows,
        "meta": {"total": len(rows)},
    }).encode())

    assert len(jobs) == 771
    assert len({j.posting_url for j in jobs}) == 771

    for job in jobs:
        assert job.posting_url == (
            "https://stripe.com/jobs/search?gh_jid="
            + job.external_id
        )


@pytest.mark.parametrize("url", [
    "https://stripe.com/jobs/search",
    "https://stripe.com/jobs/search?gh_jid=999",
    "https://stripe.com/jobs/search?gh_jid=123&gh_jid=123",
    "https://stripe.com/jobs/search?gh_jid=123&redirect=evil",
    "https://stripe.com/jobs/search?gh_jid=123#fragment",
    "https://stripe.com/jobs/search?gh_jid=%31%32%33",
    "https://stripe.com:443/jobs/search?gh_jid=123",
    "https://stripe.com.example.invalid/jobs/search?gh_jid=123",
    "https://stripe.com@evil.invalid/jobs/search?gh_jid=123",
    "https://evil.invalid@stripe.com/jobs/search?gh_jid=123",
    "http://stripe.com/jobs/search?gh_jid=123",
    "https://stripe.com/redirect?gh_jid=123",
])
def test_stripe_search_url_rejects_unsafe_variants(url):
    assert safe_link(
        url, "greenhouse", "stripe", "123",
    ) == ""


@pytest.mark.parametrize("provider,board", [
    ("greenhouse", "other-company"),
    ("lever", "stripe"),
    ("ashby", "stripe"),
])
def test_stripe_search_url_requires_correct_source(
    provider, board,
):
    assert safe_link(
        "https://stripe.com/jobs/search?gh_jid=123",
        provider, board, "123",
    ) == ""
