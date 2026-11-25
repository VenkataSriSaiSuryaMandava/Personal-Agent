"""Transactional storage for configured public job sources."""

import json
import time

from uuid import uuid4

from aegis.schemas.discovery import (
    JobSourceInput,
    MAX_REVISION,
    MAX_SOURCES,
)

from aegis.storage.database import (
    DATABASE_PATH,
    connect,
)


class SourceNotFound(Exception):
    pass


class SourceConflict(Exception):
    pass


def list_sources(user_id, path=DATABASE_PATH):
    with connect(path) as c:
        rows = c.execute("""
            SELECT
                id, provider, board, company,
                enabled, revision, created_at,
                updated_at, last_attempt_at,
                last_success_at, last_result
            FROM job_sources
            WHERE user_id = ?
            ORDER BY company COLLATE NOCASE, id
        """, (user_id,)).fetchall()

        return [dict(row) for row in rows]


def get_source(
    user_id, identifier, path=DATABASE_PATH,
):
    with connect(path) as c:
        row = c.execute("""
            SELECT
                id, provider, board, company,
                enabled, revision, created_at,
                updated_at, last_attempt_at,
                last_success_at, last_result
            FROM job_sources
            WHERE user_id = ? AND id = ?
        """, (user_id, identifier)).fetchone()

        if row is None:
            raise SourceNotFound()

        return dict(row)


def create_source(
    user_id, source, path=DATABASE_PATH,
):
    source = JobSourceInput.model_validate(
        source.model_dump()
    )

    identifier = str(uuid4())
    now = int(time.time())

    with connect(path) as c:
        c.execute("BEGIN IMMEDIATE")

        count = c.execute("""
            SELECT COUNT(*) FROM job_sources
            WHERE user_id = ?
        """, (user_id,)).fetchone()[0]

        if count >= MAX_SOURCES:
            raise SourceConflict("Source limit reached")

        existing = c.execute("""
            SELECT id FROM job_sources
            WHERE user_id = ?
            AND provider = ?
            AND board = ?
        """, (
            user_id,
            source.provider,
            source.board,
        )).fetchone()

        if existing:
            raise SourceConflict("Board already configured")

        c.execute("""
            INSERT INTO job_sources (
                id, user_id, provider, board,
                company, enabled,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            identifier,
            user_id,
            source.provider,
            source.board,
            source.company,
            int(source.enabled),
            now,
            now,
        ))

    return get_source(user_id, identifier, path)


def check_revision(row, expected_revision):
    if (
        type(expected_revision) is not int
        or not 1 <= expected_revision < MAX_REVISION
        or row["revision"] != expected_revision
    ):
        raise SourceConflict("Source changed")


def update_source(
    user_id,
    identifier,
    source,
    expected_revision,
    path=DATABASE_PATH,
):
    source = JobSourceInput.model_validate(
        source.model_dump()
    )

    with connect(path) as c:
        c.execute("BEGIN IMMEDIATE")

        row = c.execute("""
            SELECT * FROM job_sources
            WHERE user_id = ? AND id = ?
        """, (user_id, identifier)).fetchone()

        if row is None:
            raise SourceNotFound()

        check_revision(row, expected_revision)

        if (
            row["provider"] != source.provider
            or row["board"] != source.board
        ):
            raise ValueError(
                "Provider and board cannot be changed"
            )

        if (
            row["company"] != source.company
            or row["enabled"] != int(source.enabled)
        ):
            c.execute("""
                UPDATE job_sources
                SET company = ?,
                    enabled = ?,
                    revision = revision + 1,
                    updated_at = ?
                WHERE user_id = ? AND id = ?
            """, (
                source.company,
                int(source.enabled),
                max(
                    int(time.time()),
                    row["updated_at"],
                ),
                user_id,
                identifier,
            ))

    return get_source(user_id, identifier, path)


def delete_source(
    user_id,
    identifier,
    expected_revision,
    path=DATABASE_PATH,
):
    with connect(path) as c:
        c.execute("BEGIN IMMEDIATE")

        row = c.execute("""
            SELECT revision FROM job_sources
            WHERE user_id = ? AND id = ?
        """, (user_id, identifier)).fetchone()

        if row is None:
            raise SourceNotFound()

        check_revision(row, expected_revision)

        c.execute("""
            DELETE FROM job_sources
            WHERE user_id = ? AND id = ?
        """, (user_id, identifier))

    return {"deleted": True}


class CacheLimitReached(Exception):
    pass


def cache_snapshot(
    user_id,
    source_id,
    expected_revision,
    listings,
    path=DATABASE_PATH,
):
    from aegis.schemas.discovery import (
        JobListing,
        MAX_LISTINGS_PER_SOURCE,
        MAX_CACHE_BYTES,
        CACHE_RETENTION,
    )
    from aegis.services.job_adapters import safe_link

    if len(listings) > MAX_LISTINGS_PER_SOURCE:
        raise CacheLimitReached()

    listings = [
        JobListing.model_validate(item.model_dump())
        for item in listings
    ]

    identifiers = {
        item.external_id for item in listings
    }

    if len(identifiers) != len(listings):
        raise ValueError("Duplicate listing identifiers")

    now = int(time.time())

    with connect(path) as c:
        c.execute("BEGIN IMMEDIATE")

        source = c.execute("""
            SELECT * FROM job_sources
            WHERE user_id = ? AND id = ?
        """, (user_id, source_id)).fetchone()

        if source is None:
            raise SourceNotFound()

        check_revision(source, expected_revision)

        if not source["enabled"]:
            raise SourceConflict("Source disabled")

        now = max(now, source["last_success_at"] or 0)

        for item in listings:
            if not safe_link(
                item.posting_url, source["provider"],
                source["board"], item.external_id,
            ):
                raise ValueError("Unsafe posting URL")

            if item.apply_url and not safe_link(
                item.apply_url, source["provider"],
                source["board"], item.external_id,
            ):
                raise ValueError("Unsafe application URL")

        c.execute("""
            UPDATE job_listings
            SET is_open = 0
            WHERE user_id = ? AND source_id = ?
        """, (user_id, source_id))

        for item in listings:
            c.execute("""
                INSERT INTO job_listings (
                    id, user_id, source_id, external_id,
                    title, location, department, description,
                    employment_type, work_mode,
                    posting_url, apply_url, published_at,
                    first_seen_at, last_seen_at, is_open
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, 1
                )
                ON CONFLICT(
                    user_id, source_id, external_id
                ) DO UPDATE SET
                    title = excluded.title,
                    location = excluded.location,
                    department = excluded.department,
                    description = excluded.description,
                    employment_type = excluded.employment_type,
                    work_mode = excluded.work_mode,
                    posting_url = excluded.posting_url,
                    apply_url = excluded.apply_url,
                    published_at = excluded.published_at,
                    last_seen_at = excluded.last_seen_at,
                    is_open = 1
            """, (
                str(uuid4()),
                user_id,
                source_id,
                item.external_id,
                item.title,
                item.location,
                item.department,
                item.description,
                item.employment_type,
                item.work_mode,
                item.posting_url,
                item.apply_url,
                item.published_at,
                now,
                now,
            ))

        # Expire only closed cache entries.
        # Saved workspace applications are independent.
        c.execute("""
            DELETE FROM job_listings
            WHERE user_id = ?
            AND is_open = 0
            AND last_seen_at < ?
        """, (
            user_id,
            now - CACHE_RETENTION,
        ))

        size = c.execute("""
            SELECT COALESCE(SUM(
                length(CAST(id AS BLOB)) +
                length(CAST(source_id AS BLOB)) +
                length(CAST(external_id AS BLOB)) +
                length(CAST(title AS BLOB)) +
                length(CAST(location AS BLOB)) +
                length(CAST(department AS BLOB)) +
                length(CAST(description AS BLOB)) +
                length(CAST(employment_type AS BLOB)) +
                length(CAST(work_mode AS BLOB)) +
                length(CAST(posting_url AS BLOB)) +
                length(CAST(apply_url AS BLOB)) + 128
            ), 0)
            FROM job_listings
            WHERE user_id = ?
        """, (user_id,)).fetchone()[0]

        if size > MAX_CACHE_BYTES:
            raise CacheLimitReached()

        c.execute("""
            UPDATE job_sources
            SET last_attempt_at = ?,
                last_success_at = ?,
                last_result = 'success'
            WHERE user_id = ? AND id = ?
        """, (
            now, now, user_id, source_id,
        ))

    return {
        "result": "success",
        "count": len(listings),
        "refreshed_at": now,
    }


def record_refresh_failure(
    user_id,
    source_id,
    expected_revision,
    result,
    path=DATABASE_PATH,
):
    if result not in {"failed", "limited"}:
        raise ValueError("Invalid refresh result")

    with connect(path) as c:
        c.execute("BEGIN IMMEDIATE")

        row = c.execute("""
            SELECT revision, enabled, last_attempt_at
            FROM job_sources
            WHERE user_id = ? AND id = ?
        """, (user_id, source_id)).fetchone()

        if row is None:
            raise SourceNotFound()

        check_revision(row, expected_revision)

        if not row["enabled"]:
            raise SourceConflict("Source disabled")

        now = max(
            int(time.time()),
            row["last_attempt_at"] or 0,
        )

        c.execute("""
            UPDATE job_sources
            SET last_attempt_at = ?,
                last_result = ?
            WHERE user_id = ? AND id = ?
        """, (
            now, result, user_id, source_id,
        ))


def list_jobs(
    user_id,
    path=DATABASE_PATH,
    *,
    query="",
    provider=None,
    location="",
    freshness="all",
    limit=50,
    offset=0,
):
    from aegis.schemas.discovery import CACHE_TTL

    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid limit")

    if (
        type(offset) is not int
        or not 0 <= offset <= 1000000
    ):
        raise ValueError("Invalid offset")

    if (
        not isinstance(query, str)
        or len(query) > 200
    ):
        raise ValueError("Invalid query")

    if provider not in (
        None, "greenhouse", "lever", "ashby",
    ):
        raise ValueError("Invalid provider")

    if (
        not isinstance(location, str)
        or len(location) > 200
    ):
        raise ValueError("Invalid location")

    if freshness not in {"all", "fresh", "stale"}:
        raise ValueError("Invalid freshness")

    terms = list(dict.fromkeys(query.lower().split()))
    query = json.dumps(terms)
    location = location.strip().lower()

    now = int(time.time())

    with connect(path) as c:
        c.execute("BEGIN")

        rows = c.execute("""
            SELECT
                j.id, j.source_id, j.external_id,
                j.title, j.location, j.department,
                j.employment_type, j.work_mode,
                j.posting_url, j.apply_url,
                j.published_at, j.first_seen_at,
                j.last_seen_at,
                s.company, s.provider, s.board,
                s.last_success_at, s.last_result,
                a.application_id
            FROM job_listings j
            JOIN job_sources s
                ON s.id = j.source_id
                AND s.user_id = j.user_id
            LEFT JOIN job_application_links a
                ON a.user_id = j.user_id
                AND a.provider = s.provider
                AND a.board = s.board
                AND a.external_id = j.external_id
            WHERE j.user_id = ?
                AND j.is_open = 1
                AND s.enabled = 1
                AND (? IS NULL OR s.provider = ?)
                AND (
                    ? = ''
                    OR instr(lower(j.location), ?) > 0
                )
                AND (
                    ? = 'all'
                    OR (
                        ? = 'fresh'
                        AND s.last_success_at IS NOT NULL
                        AND s.last_success_at > ?
                        AND s.last_success_at <= ?
                    )
                    OR (
                        ? = 'stale'
                        AND (
                            s.last_success_at IS NULL
                            OR s.last_success_at <= ?
                            OR s.last_success_at > ?
                        )
                    )
                )
                AND NOT EXISTS (
                    SELECT 1 FROM json_each(?) term
                    WHERE instr(lower(j.title), term.value) = 0
                    AND instr(lower(s.company), term.value) = 0
                    AND instr(lower(j.location), term.value) = 0
                    AND instr(lower(j.department), term.value) = 0
                    AND instr(lower(j.description), term.value) = 0
                )
            ORDER BY
                COALESCE(
                    j.published_at, j.first_seen_at
                ) DESC,
                j.id DESC
            LIMIT ? OFFSET ?
        """, (
            user_id,
            provider, provider,
            location, location,
            freshness,
            freshness, now - CACHE_TTL, now,
            freshness, now - CACHE_TTL, now,
            query,
            limit + 1, offset,
        )).fetchall()

    jobs = []

    for row in rows[:limit]:
        item = dict(row)

        item["stale"] = (
            item["last_success_at"] is None
            or not 0 <= now - item["last_success_at"] < CACHE_TTL
        )

        jobs.append(item)

    return {
        "jobs": jobs,
        "next_offset": (
            offset + limit
            if len(rows) > limit
            else None
        ),
    }


def get_job(user_id, identifier, path=DATABASE_PATH):
    from aegis.schemas.discovery import CACHE_TTL

    with connect(path) as c:
        row = c.execute("""
            SELECT
                j.*,
                s.company, s.provider, s.board,
                s.last_success_at, s.last_result,
                a.application_id
            FROM job_listings j
            JOIN job_sources s
                ON s.id = j.source_id
                AND s.user_id = j.user_id
            LEFT JOIN job_application_links a
                ON a.user_id = j.user_id
                AND a.provider = s.provider
                AND a.board = s.board
                AND a.external_id = j.external_id
            WHERE j.user_id = ? AND j.id = ?
                AND s.enabled = 1
                AND j.is_open = 1
        """, (user_id, identifier)).fetchone()

    if row is None:
        raise SourceNotFound()

    result = dict(row)
    result.pop("user_id")

    result["stale"] = (
        result["last_success_at"] is None
        or not 0 <= (
            int(time.time()) - result["last_success_at"]
        ) < CACHE_TTL
    )

    return result


def save_job(user_id, identifier, path=DATABASE_PATH):
    from aegis.schemas.workspaces import (
        WorkspaceRecord,
        validate_record,
    )
    from aegis.services.job_adapters import safe_link

    with connect(path) as c:
        c.execute("BEGIN IMMEDIATE")

        job = c.execute("""
            SELECT
                j.*,
                s.provider, s.board, s.company
            FROM job_listings j
            JOIN job_sources s
                ON s.id = j.source_id
                AND s.user_id = j.user_id
            WHERE j.user_id = ?
                AND j.id = ?
                AND j.is_open = 1
                AND s.enabled = 1
        """, (user_id, identifier)).fetchone()

        if job is None:
            raise SourceNotFound()

        existing = c.execute("""
            SELECT application_id
            FROM job_application_links
            WHERE user_id = ?
                AND provider = ?
                AND board = ?
                AND external_id = ?
        """, (
            user_id,
            job["provider"],
            job["board"],
            job["external_id"],
        )).fetchone()

        if existing:
            return {
                "application_id": existing["application_id"],
                "created": False,
            }

        url = safe_link(
            job["posting_url"],
            job["provider"],
            job["board"],
            job["external_id"],
        )

        if not url:
            raise ValueError("Unsafe posting URL")

        # Match existing manually saved postings by exact URL.
        existing = c.execute("""
            SELECT id FROM workspace_records
            WHERE user_id = ?
                AND workspace = 'jobs'
                AND json_extract(payload, '$.reference') = ?
            ORDER BY created_at, id
            LIMIT 1
        """, (user_id, url)).fetchone()

        if existing:
            application_id = existing["id"]

            linked = c.execute("""
                SELECT 1 FROM job_application_links
                WHERE application_id = ?
            """, (application_id,)).fetchone()

            if linked:
                return {
                    "application_id": application_id,
                    "created": False,
                }

        else:
            application_id = str(uuid4())

        now = int(time.time())

        if existing is None:
            notes = (
                "Discovered via " + job["provider"]
                + "\nLocation: " + job["location"]
                + "\n\n" + job["description"]
            )[:8000]

            record = validate_record(
                "jobs",
                WorkspaceRecord(
                    title=job["title"],
                    detail=job["company"],
                    status="saved",
                    reference=url,
                    notes=notes,
                ),
            )

            c.execute("""
                INSERT INTO workspace_records (
                    id, user_id, workspace,
                    payload, revision,
                    created_at, updated_at
                )
                VALUES (?, ?, 'jobs', ?, 1, ?, ?)
            """, (
                application_id,
                user_id,
                record.model_dump_json(),
                now,
                now,
            ))

        c.execute("""
            INSERT INTO job_application_links (
                user_id, application_id,
                provider, board,
                external_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            application_id,
            job["provider"],
            job["board"],
            job["external_id"],
            now,
        ))

        return {
            "application_id": application_id,
            "created": existing is None,
        }
