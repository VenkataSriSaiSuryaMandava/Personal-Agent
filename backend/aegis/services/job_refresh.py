"""On-demand job-board refresh with snapshot preservation."""

import time

from threading import Lock

from aegis.schemas.discovery import (
    JobSourceInput,
    CACHE_TTL,
)

from aegis.services.job_fetcher import (
    fetch_jobs,
    SourceFetchFailed,
    SourceBoardLimited,
    SourceDataRejected,
    SourceFetchBusy,
)

from aegis.storage import discovery as storage
from aegis.storage.database import DATABASE_PATH
from aegis.storage.settings import load_settings


class DiscoveryStopped(Exception):
    pass


def require_discovery_enabled(path):
    if load_settings(path).settings.emergency_stop:
        raise DiscoveryStopped()


REFRESH_LOCK = Lock()
ACTIVE_REFRESHES = set()

MIN_REFRESH_INTERVAL = 60


def refresh_source(
    user_id,
    identifier,
    path=DATABASE_PATH,
    *,
    force=False,
    expected_revision=None,
    before_write=None,
):
    if type(force) is not bool:
        raise ValueError("Invalid refresh option")

    key = (str(path), user_id, identifier)

    with REFRESH_LOCK:
        if key in ACTIVE_REFRESHES:
            raise SourceFetchBusy()

        ACTIVE_REFRESHES.add(key)

    try:
        row = storage.get_source(
            user_id, identifier, path,
        )

        if expected_revision is not None:
            storage.check_revision(row, expected_revision)

        if not row["enabled"]:
            raise storage.SourceConflict(
                "Source disabled"
            )

        now = int(time.time())
        success = row["last_success_at"]
        attempted = row["last_attempt_at"]

        if (
            not force
            and success is not None
            and 0 <= now - success < CACHE_TTL
        ):
            return {
                "result": "cached",
                "refreshed_at": success,
            }

        if (
            attempted is not None
            and 0 <= now - attempted
            < MIN_REFRESH_INTERVAL
        ):
            return {
                "result": "cooldown",
                "refreshed_at": success,
            }

        revision = row["revision"]

        source = JobSourceInput(
            provider=row["provider"],
            board=row["board"],
            company=row["company"],
            enabled=bool(row["enabled"]),
        )

        try:
            if before_write is not None:
                before_write()

            require_discovery_enabled(path)

            listings = fetch_jobs(source)

        except SourceFetchFailed as exc:
            reason = "provider_unavailable"
            result = "failed"

            if isinstance(exc, SourceBoardLimited):
                reason = "board_limit"
                result = "limited"
            elif isinstance(exc, SourceDataRejected):
                reason = "response_rejected"

            if before_write is not None:
                before_write()

            storage.record_refresh_failure(
                user_id, identifier,
                revision, result, path,
            )

            return {
                "result": result,
                "reason": reason,
                "refreshed_at": success,
            }

        if before_write is not None:
            before_write()

        try:
            return storage.cache_snapshot(
                user_id,
                identifier,
                revision,
                listings,
                path,
            )

        except storage.CacheLimitReached:
            storage.record_refresh_failure(
                user_id, identifier,
                revision, "limited", path,
            )

            return {
                "result": "limited",
                "reason": "cache_limit",
                "refreshed_at": success,
            }

    finally:
        with REFRESH_LOCK:
            ACTIVE_REFRESHES.discard(key)
