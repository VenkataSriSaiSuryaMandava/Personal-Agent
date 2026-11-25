"""Bounded subprocess orchestration for public job discovery."""

import json
import subprocess
import sys

from threading import BoundedSemaphore

from aegis.schemas.discovery import (
    JobSourceInput,
    MAX_CONCURRENT_REQUESTS,
    MAX_RESPONSE_BYTES,
    REQUEST_TIMEOUT,
)

from aegis.services.job_adapters import (
    normalize_response,
    SourceResponseRejected,
    BoardLimitExceeded,
)


FETCH_SLOTS = BoundedSemaphore(
    MAX_CONCURRENT_REQUESTS
)


class SourceFetchFailed(Exception):
    pass


class SourceBoardLimited(SourceFetchFailed):
    pass


class SourceDataRejected(SourceFetchFailed):
    pass


class SourceFetchBusy(Exception):
    pass


def fetch_jobs(source):
    source = JobSourceInput.model_validate(
        source.model_dump()
    )

    if not source.enabled:
        raise SourceFetchFailed(
            "Source disabled"
        )

    if not FETCH_SLOTS.acquire(blocking=False):
        raise SourceFetchBusy()

    try:
        # Never send profile data, session tokens, source labels,
        # application history or inherited environment secrets.
        payload = json.dumps({
            "provider": source.provider,
            "board": source.board,
        }).encode("utf-8")

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-m",
                    "aegis.services.job_fetch_worker",
                ],
                input=payload,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=REQUEST_TIMEOUT,
                check=False,
                env={
                    "PYTHONIOENCODING": "utf-8",
                },
            )

        except (
            subprocess.TimeoutExpired,
            OSError,
        ):
            raise SourceFetchFailed(
                "Source unavailable"
            ) from None

        if (
            result.returncode != 0
            or not isinstance(result.stdout, bytes)
            or not 1 <= len(result.stdout)
            <= MAX_RESPONSE_BYTES
        ):
            raise SourceFetchFailed(
                "Source unavailable"
            )

        try:
            return normalize_response(
                source,
                result.stdout,
            )

        except BoardLimitExceeded:
            raise SourceBoardLimited() from None

        except SourceResponseRejected:
            raise SourceDataRejected(
                "Source response rejected"
            ) from None

    finally:
        FETCH_SLOTS.release()
