import pytest

from aegis.schemas import discovery as schemas
from aegis.schemas.discovery import (
    JobSourceInput,
    JobListing,
    CACHE_RETENTION,
)

from aegis.services import job_refresh

from aegis.services.job_fetcher import (
    SourceFetchBusy,
    SourceFetchFailed,
)

from aegis.storage import discovery as storage
from aegis.storage.database import connect


@pytest.fixture
def cache(authenticated_environment):
    _, _, _, path, _ = authenticated_environment

    source = storage.create_source(
        1,
        JobSourceInput(
            provider="lever",
            board="synthetic",
            company="Synthetic Company",
        ),
        path,
    )

    return path, source


def listing(external_id="example", **changes):
    payload = {
        "external_id": external_id,
        "title": "Software Engineer",
        "location": "San Francisco",
        "description": "Python and SQL",
        "posting_url":
            f"https://jobs.lever.co/synthetic/{external_id}",
    }

    payload.update(changes)

    return JobListing(**payload)


def snapshot(cache, jobs):
    path, source = cache

    return storage.cache_snapshot(
        1, source["id"], source["revision"],
        jobs, path,
    )


def test_snapshot_updates_existing_listing(cache):
    path, _ = cache

    snapshot(cache, [listing()])

    original = storage.list_jobs(
        1, path,
    )["jobs"][0]

    snapshot(cache, [
        listing(title="Senior Software Engineer"),
    ])

    jobs = storage.list_jobs(1, path)["jobs"]

    assert len(jobs) == 1
    assert jobs[0]["id"] == original["id"]
    assert jobs[0]["title"] == "Senior Software Engineer"

    assert (
        jobs[0]["first_seen_at"]
        == original["first_seen_at"]
    )


def test_closed_and_reopened_listing(cache):
    path, _ = cache

    snapshot(cache, [listing()])

    original = storage.list_jobs(
        1, path,
    )["jobs"][0]

    snapshot(cache, [])

    assert storage.list_jobs(
        1, path,
    )["jobs"] == []

    snapshot(cache, [listing()])

    assert storage.list_jobs(
        1, path,
    )["jobs"][0]["id"] == original["id"]


def test_closed_listing_expiration(
    cache, monkeypatch,
):
    path, _ = cache

    snapshot(cache, [listing()])

    now = storage.list_jobs(
        1, path,
    )["jobs"][0]["last_seen_at"]

    monkeypatch.setattr(
        storage.time,
        "time",
        lambda: now + CACHE_RETENTION + 1,
    )

    snapshot(cache, [])

    with connect(path) as c:
        assert c.execute("""
            SELECT COUNT(*) FROM job_listings
        """).fetchone()[0] == 0


def test_cache_budget_rolls_back(
    cache, monkeypatch,
):
    path, source = cache

    snapshot(cache, [listing()])

    before = storage.list_jobs(1, path)
    previous = storage.get_source(
        1, source["id"], path,
    )

    monkeypatch.setattr(
        schemas,
        "MAX_CACHE_BYTES",
        1,
    )

    with pytest.raises(storage.CacheLimitReached):
        snapshot(cache, [listing("replacement")])

    assert storage.list_jobs(1, path) == before

    assert storage.get_source(
        1, source["id"], path,
    ) == previous


def test_search_pagination_and_detail(cache):
    path, _ = cache

    snapshot(cache, [
        listing("one"),
        listing(
            "two",
            title="Data Engineer",
            description="Apache Spark",
        ),
    ])

    page = storage.list_jobs(
        1, path, limit=1,
    )

    assert len(page["jobs"]) == 1
    assert page["next_offset"] == 1
    assert "description" not in page["jobs"][0]

    assert len(storage.list_jobs(
        1, path, limit=1, offset=1,
    )["jobs"]) == 1

    jobs = storage.list_jobs(
        1, path, query="spark",
    )["jobs"]

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Data Engineer"

    assert storage.get_job(
        1, jobs[0]["id"], path,
    )["description"] == "Apache Spark"

    assert storage.list_jobs(
        1, path, provider="ashby",
    )["jobs"] == []


def test_cache_owner_isolation(cache):
    path, _ = cache

    snapshot(cache, [listing()])

    job = storage.list_jobs(
        1, path,
    )["jobs"][0]

    assert storage.list_jobs(
        2, path,
    )["jobs"] == []

    with pytest.raises(storage.SourceNotFound):
        storage.get_job(2, job["id"], path)


def test_disabled_source_hidden(cache):
    path, source = cache

    snapshot(cache, [listing()])

    storage.update_source(
        1,
        source["id"],
        JobSourceInput(
            provider="lever",
            board="synthetic",
            company="Synthetic Company",
            enabled=False,
        ),
        1,
        path,
    )

    assert storage.list_jobs(
        1, path,
    )["jobs"] == []

    with pytest.raises(storage.SourceConflict):
        snapshot(cache, [listing()])


def test_unsafe_url_rolls_back(cache):
    path, _ = cache

    snapshot(cache, [listing()])

    before = storage.list_jobs(1, path)

    with pytest.raises(ValueError):
        snapshot(cache, [
            listing(
                posting_url="javascript:alert(1)",
            ),
        ])

    assert storage.list_jobs(1, path) == before


def test_refresh_uses_fresh_cache(
    cache, monkeypatch,
):
    path, source = cache

    snapshot(cache, [listing()])

    def unexpected(*args):
        pytest.fail("Unexpected provider request")

    monkeypatch.setattr(
        job_refresh, "fetch_jobs", unexpected,
    )

    result = job_refresh.refresh_source(
        1, source["id"], path,
    )

    assert result["result"] == "cached"


def test_forced_refresh_cooldown(
    cache, monkeypatch,
):
    path, source = cache

    snapshot(cache, [listing()])

    def unexpected(*args):
        pytest.fail("Unexpected provider request")

    monkeypatch.setattr(
        job_refresh, "fetch_jobs", unexpected,
    )

    result = job_refresh.refresh_source(
        1, source["id"], path, force=True,
    )

    assert result["result"] == "cooldown"


def test_failed_refresh_preserves_snapshot(
    cache, monkeypatch,
):
    path, source = cache

    snapshot(cache, [listing()])

    with connect(path) as c:
        c.execute("""
            UPDATE job_sources
            SET last_attempt_at = 1
            WHERE id = ?
        """, (source["id"],))

    def fail(*args):
        raise SourceFetchFailed()

    monkeypatch.setattr(
        job_refresh, "fetch_jobs", fail,
    )

    before = storage.get_source(
        1, source["id"], path,
    )

    result = job_refresh.refresh_source(
        1, source["id"], path, force=True,
    )

    assert result["result"] == "failed"

    after = storage.get_source(
        1, source["id"], path,
    )

    assert after["last_result"] == "failed"

    assert (
        after["last_success_at"]
        == before["last_success_at"]
    )

    assert len(storage.list_jobs(
        1, path,
    )["jobs"]) == 1


def test_refresh_success(cache, monkeypatch):
    path, source = cache

    monkeypatch.setattr(
        job_refresh,
        "fetch_jobs",
        lambda source: [listing()],
    )

    result = job_refresh.refresh_source(
        1, source["id"], path,
    )

    assert result["result"] == "success"
    assert result["count"] == 1


def test_refresh_reauthorization(
    cache, monkeypatch,
):
    path, source = cache

    monkeypatch.setattr(
        job_refresh,
        "fetch_jobs",
        lambda source: [listing()],
    )

    def revoked():
        raise PermissionError("Session revoked")

    with pytest.raises(PermissionError):
        job_refresh.refresh_source(
            1, source["id"], path,
            before_write=revoked,
        )

    assert storage.list_jobs(
        1, path,
    )["jobs"] == []

    assert not job_refresh.ACTIVE_REFRESHES


def test_same_source_refresh_exclusion(
    cache, monkeypatch,
):
    path, source = cache

    def nested_refresh(config):
        with pytest.raises(SourceFetchBusy):
            job_refresh.refresh_source(
                1, source["id"], path,
            )

        return [listing()]

    monkeypatch.setattr(
        job_refresh,
        "fetch_jobs",
        nested_refresh,
    )

    result = job_refresh.refresh_source(
        1, source["id"], path,
    )

    assert result["result"] == "success"
    assert not job_refresh.ACTIVE_REFRESHES


def test_stale_source_snapshot_rejected(cache):
    path, source = cache

    storage.update_source(
        1,
        source["id"],
        JobSourceInput(
            provider="lever",
            board="synthetic",
            company="Updated label",
        ),
        1,
        path,
    )

    with pytest.raises(storage.SourceConflict):
        snapshot(cache, [listing()])


def test_location_filter_before_pagination(cache):
    path, _ = cache

    snapshot(cache, [
        listing("sf", location="San Francisco"),
        listing("ny", location="New York"),
        listing("remote", location="Remote"),
    ])

    result = storage.list_jobs(
        1, path, location="francisco", limit=1,
    )

    assert len(result["jobs"]) == 1
    assert result["jobs"][0]["external_id"] == "sf"
    assert result["next_offset"] is None


def test_freshness_filter(cache, monkeypatch):
    path, source = cache

    snapshot(cache, [listing()])

    assert len(storage.list_jobs(
        1, path, freshness="fresh",
    )["jobs"]) == 1

    assert storage.list_jobs(
        1, path, freshness="stale",
    )["jobs"] == []

    source = storage.get_source(
        1, source["id"], path,
    )

    monkeypatch.setattr(
        storage.time,
        "time",
        lambda: (
            source["last_success_at"]
            + schemas.CACHE_TTL
        ),
    )

    assert storage.list_jobs(
        1, path, freshness="fresh",
    )["jobs"] == []

    result = storage.list_jobs(
        1, path, freshness="stale",
    )

    assert len(result["jobs"]) == 1
    assert result["jobs"][0]["stale"] is True


def test_stale_refresh_revision_rejected_before_fetch(
    cache, monkeypatch,
):
    path, source = cache

    storage.update_source(
        1,
        source["id"],
        JobSourceInput(
            provider="lever",
            board="synthetic",
            company="Changed company",
        ),
        1,
        path,
    )

    def unexpected(*args):
        pytest.fail("Stale revision performed network request")

    monkeypatch.setattr(
        job_refresh, "fetch_jobs", unexpected,
    )

    with pytest.raises(storage.SourceConflict):
        job_refresh.refresh_source(
            1,
            source["id"],
            path,
            expected_revision=1,
        )

    assert not job_refresh.ACTIVE_REFRESHES


def test_stripe_cache_and_application_integration(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    source = storage.create_source(
        1,
        JobSourceInput(
            provider="greenhouse",
            board="stripe",
            company="Stripe",
        ),
        path,
    )

    jobs = [
        listing(
            str(index),
            posting_url=(
                "https://stripe.com/careers/listing/"
                f"software-engineer/{index}"
            ),
        )
        for index in range(771)
    ]

    result = storage.cache_snapshot(
        1, source["id"], source["revision"],
        jobs, path,
    )

    assert result["count"] == 771

    job = storage.list_jobs(1, path)["jobs"][0]

    saved = storage.save_job(1, job["id"], path)
    duplicate = storage.save_job(1, job["id"], path)

    assert saved["created"]
    assert not duplicate["created"]
    assert saved["application_id"] == duplicate["application_id"]

    with pytest.raises(storage.CacheLimitReached):
        storage.cache_snapshot(
            1, source["id"], source["revision"],
            jobs * 2, path,
        )

    with connect(path) as c:
        assert c.execute("""
            SELECT COUNT(*) FROM job_listings
            WHERE source_id = ? AND is_open = 1
        """, (source["id"],)).fetchone()[0] == 771


def test_multi_keyword_search_across_fields(cache):
    path, _ = cache

    snapshot(cache, [
        listing(
            "python",
            title="Software Engineer",
            description="Python and distributed systems",
        ),
        listing(
            "java",
            title="Software Engineer",
            description="Java development",
        ),
        listing(
            "analyst",
            title="Data Analyst",
            description="Python reporting",
        ),
    ])

    for query in (
        "Python software engineer",
        "ENGINEER   python Software",
        "python python engineer",
    ):
        result = storage.list_jobs(
            1, path, query=query, limit=1,
        )

        assert len(result["jobs"]) == 1
        assert result["jobs"][0]["external_id"] == "python"
        assert result["next_offset"] is None

    assert storage.list_jobs(
        1, path, query="python nonexistent",
    )["jobs"] == []

    assert len(storage.list_jobs(
        1, path, query="   ",
    )["jobs"]) == 3


@pytest.mark.parametrize("exception_name,reason,result", [
    ("SourceFetchFailed", "provider_unavailable", "failed"),
    ("SourceBoardLimited", "board_limit", "limited"),
    ("SourceDataRejected", "response_rejected", "failed"),
])
def test_safe_refresh_failure_reason(
    cache, monkeypatch, exception_name, reason, result,
):
    from aegis.services import job_fetcher

    path, source = cache
    snapshot(cache, [listing()])

    with connect(path) as c:
        c.execute("""
            UPDATE job_sources
            SET last_attempt_at = 1
            WHERE id = ?
        """, (source["id"],))

    def fail(*args):
        raise getattr(job_fetcher, exception_name)(
            "Synthetic internal error details"
        )

    monkeypatch.setattr(job_refresh, "fetch_jobs", fail)

    response = job_refresh.refresh_source(
        1, source["id"], path, force=True,
    )

    assert response["result"] == result
    assert response["reason"] == reason
    assert "Synthetic internal error" not in str(response)

    assert len(storage.list_jobs(1, path)["jobs"]) == 1
