"""Private career discovery endpoints."""

import sqlite3
import unicodedata

from threading import BoundedSemaphore

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from aegis.api import auth
from aegis.security.request_storage import request_database
from aegis.api.auth import deny

from aegis.api.conversation_history import (
    authorize,
    respond,
    valid_id,
)

from aegis.api.career import (
    no_query,
    read_payload,
    reauthorize,
)

from aegis.api.workspaces import number

from aegis.schemas.discovery import (
    JobSourceInput,
    SourceAction,
    SaveJobInput,
)

from aegis.services.job_fetcher import SourceFetchBusy
from aegis.services.job_refresh import (
    DiscoveryStopped,
    refresh_source,
)
from aegis.services.career_intelligence import analyze_job
from aegis.storage import discovery as storage


router = APIRouter(
    prefix="/api/v1/career",
    tags=["private job discovery"],
)

BODY_LIMIT = 8192
MATCH_SLOT = BoundedSemaphore(1)


def execute(operation, *args, **kwargs):
    try:
        return operation(
            *args,
            path=request_database(auth.service.path),
            **kwargs,
        )

    except storage.SourceNotFound:
        deny(404, "Discovery record not found")

    except storage.SourceConflict:
        deny(409, "Source changed or limit reached")

    except DiscoveryStopped:
        deny(403, "Emergency stop is active")

    except SourceFetchBusy:
        deny(429, "Job refresh busy")

    except ValidationError:
        deny(503, "Discovery storage unavailable")

    except ValueError:
        deny(422, "Invalid discovery request")

    except (sqlite3.Error, OSError, RuntimeError):
        deny(503, "Discovery storage unavailable")


@router.get("/sources")
def sources(
    request: Request,
    user_id: int = Depends(authorize),
):
    no_query(request)

    return respond({
        "sources": execute(
            storage.list_sources,
            user_id,
        ),
    })


@router.post("/sources")
async def create_source(
    request: Request,
    user_id: int = Depends(authorize),
):
    no_query(request)

    payload = await read_payload(
        request,
        JobSourceInput,
        BODY_LIMIT,
    )

    await run_in_threadpool(
        reauthorize, request, user_id,
    )

    return respond(await run_in_threadpool(
        execute,
        storage.create_source,
        user_id,
        payload,
    ))


@router.post("/source")
async def source_action(
    request: Request,
    user_id: int = Depends(authorize),
):
    no_query(request)

    payload = await read_payload(
        request,
        SourceAction,
        BODY_LIMIT,
    )

    identifier = valid_id(payload.id)

    if payload.action == "update":
        if payload.source is None or payload.force:
            deny(422, "Invalid source update")

    elif payload.source is not None:
        deny(422, "Unexpected source data")

    if payload.action == "delete" and payload.force:
        deny(422, "Invalid delete option")

    await run_in_threadpool(
        reauthorize, request, user_id,
    )

    if payload.action == "update":
        return respond(await run_in_threadpool(
            execute,
            storage.update_source,
            user_id,
            identifier,
            payload.source,
            payload.expected_revision,
        ))

    if payload.action == "delete":
        return respond(await run_in_threadpool(
            execute,
            storage.delete_source,
            user_id,
            identifier,
            payload.expected_revision,
        ))

    def refresh():
        row = execute(
            storage.get_source,
            user_id,
            identifier,
        )

        if row["revision"] != payload.expected_revision:
            deny(409, "Source changed")

        reauthorize(request, user_id)

        return execute(
            refresh_source,
            user_id,
            identifier,
            force=payload.force,
            expected_revision=payload.expected_revision,
            before_write=lambda: reauthorize(
                request, user_id,
            ),
        )

    return respond(
        await run_in_threadpool(refresh)
    )


@router.get("/jobs")
def jobs(
    request: Request,
    user_id: int = Depends(authorize),
):
    allowed = {
        "q", "provider", "location", "freshness", "limit", "offset",
    }

    params = list(
        request.query_params.multi_items()
    )

    keys = [key for key, _ in params]

    if (
        not set(keys).issubset(allowed)
        or len(keys) != len(set(keys))
    ):
        deny(422, "Invalid query")

    query = request.query_params.get("q", "")
    location = request.query_params.get("location", "")
    freshness = request.query_params.get("freshness", "all")

    if (
        len(location) > 200
        or any(
            unicodedata.category(char) in {"Cc", "Cf"}
            for char in location
        )
    ):
        deny(422, "Invalid location")

    if freshness not in {"all", "fresh", "stale"}:
        deny(422, "Invalid freshness")
    provider = request.query_params.get(
        "provider",
    )

    if (
        len(query) > 200
        or any(
            unicodedata.category(char)
            in {"Cc", "Cf"}
            for char in query
        )
    ):
        deny(422, "Invalid search")

    if provider not in (
        None, "greenhouse", "lever", "ashby",
    ):
        deny(422, "Invalid provider")

    limit = number(
        request, "limit", 50, 1, 100,
    )

    offset = number(
        request, "offset", 0, 0, 1000000,
    )

    return respond(execute(
        storage.list_jobs,
        user_id,
        query=query,
        provider=provider,
        location=location,
        freshness=freshness,
        limit=limit,
        offset=offset,
    ))


@router.get("/job")
def job(
    request: Request,
    user_id: int = Depends(authorize),
):
    params = list(
        request.query_params.multi_items()
    )

    if len(params) != 1 or params[0][0] != "id":
        deny(422, "Invalid query")

    return respond(execute(
        storage.get_job,
        user_id,
        valid_id(params[0][1]),
    ))


@router.post("/job")
async def save_job(
    request: Request,
    user_id: int = Depends(authorize),
):
    no_query(request)

    payload = await read_payload(
        request,
        SaveJobInput,
        BODY_LIMIT,
    )

    identifier = valid_id(payload.id)

    await run_in_threadpool(
        reauthorize, request, user_id,
    )

    return respond(await run_in_threadpool(
        execute,
        storage.save_job,
        user_id,
        identifier,
    ))


@router.get("/match")
def job_match(
    request: Request,
    user_id: int = Depends(authorize),
):
    params = list(
        request.query_params.multi_items()
    )

    if len(params) != 1 or params[0][0] != "id":
        deny(422, "Invalid query")

    identifier = valid_id(params[0][1])

    if not MATCH_SLOT.acquire(blocking=False):
        deny(429, "Job matching busy")

    try:
        result = execute(
            analyze_job,
            user_id,
            identifier,
        )

        reauthorize(request, user_id)

        return respond(result)

    finally:
        MATCH_SLOT.release()
