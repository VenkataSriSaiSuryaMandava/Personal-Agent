"""Authenticated, explicitly triggered local workflows."""

import sqlite3

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from aegis.api import auth
from aegis.api.auth import deny
from aegis.api.career import (
    no_query,
    read_payload,
    reauthorize,
)
from aegis.api.conversation_history import (
    authorize,
    respond,
    valid_id,
)
from aegis.api.discovery import MATCH_SLOT
from aegis.api.workspaces import number

from aegis.schemas.workflows import (
    WorkflowCreate,
    WorkflowCancel,
)

from aegis.security.request_storage import request_database

from aegis.services.agents.execution import (
    execute_workflow,
    WorkflowBusy,
)
from aegis.services.agents.permissions import (
    CapabilityDenied,
    authorize_local_capability,
)
from aegis.services.career_intelligence import analyze_job
from aegis.services.company_intelligence import (
    get_company_intelligence,
)

from aegis.storage import workflows as storage
from aegis.storage.discovery import SourceNotFound
from aegis.storage.settings import (
    SettingsUnavailable,
    load_settings,
)


router = APIRouter(
    prefix="/api/v1/workflows",
    tags=["local agent workflows"],
)

BODY_LIMIT = 4096


def company_handler(user_id, parameters, path):
    try:
        return get_company_intelligence(
            user_id,
            str(parameters.source_id),
            path,
        )

    except SourceNotFound:
        raise LookupError("Target unavailable") from None


def match_handler(user_id, parameters, path):
    try:
        result = analyze_job(
            user_id,
            str(parameters.listing_id),
            path,
        )

        return result["matching"]

    except SourceNotFound:
        raise LookupError("Target unavailable") from None


HANDLERS = {
    "career.company_summary": company_handler,
    "career.match_listing": match_handler,
}


def execute(operation, *args, **kwargs):
    try:
        return operation(
            *args,
            path=request_database(auth.service.path),
            **kwargs,
        )

    except storage.WorkflowNotFound:
        deny(404, "Workflow or target not found")

    except (
        storage.WorkflowConflict,
        storage.WorkflowLeaseLost,
    ):
        deny(409, "Workflow changed; reload")

    except (
        storage.WorkflowCapacityReached,
        WorkflowBusy,
    ):
        deny(429, "Workflow capacity reached or busy")

    except CapabilityDenied:
        deny(403, "Workflow operation denied")

    except (
        ValidationError,
        SettingsUnavailable,
        sqlite3.Error,
        OSError,
        RuntimeError,
    ):
        deny(503, "Workflow unavailable")

    except ValueError:
        deny(422, "Invalid workflow request")


def validate_query(request, allowed):
    keys = [
        key for key, _
        in request.query_params.multi_items()
    ]

    if (
        not set(keys).issubset(allowed)
        or len(keys) != len(set(keys))
    ):
        deny(422, "Invalid workflow query")


def create_authorized(user_id, payload, path):
    capability = storage.WORKFLOW_CAPABILITIES[
        payload.workflow_type
    ]

    authorize_local_capability(
        capability,
        emergency_stop=load_settings(path)
            .settings.emergency_stop,
        scoped_grant=True,
    )

    return storage.create_workflow(
        user_id, payload, path,
    )


@router.get("")
def workflows(
    request: Request,
    user_id: int = Depends(authorize),
):
    validate_query(request, {"limit", "offset"})

    return respond(execute(
        storage.list_workflows,
        user_id,
        limit=number(
            request, "limit", 50, 1, 100,
        ),
        offset=number(
            request, "offset", 0, 0, 1000,
        ),
    ))


@router.post("")
async def create(
    request: Request,
    user_id: int = Depends(authorize),
):
    no_query(request)

    payload = await read_payload(
        request, WorkflowCreate, BODY_LIMIT,
    )

    def operation():
        reauthorize(request, user_id)

        result = execute(
            create_authorized,
            user_id,
            payload,
        )

        reauthorize(request, user_id)

        return result

    return respond(
        await run_in_threadpool(operation)
    )


@router.get("/{run_id}")
def detail(
    run_id: str,
    request: Request,
    user_id: int = Depends(authorize),
):
    no_query(request)

    result = execute(
        storage.get_workflow,
        user_id,
        valid_id(run_id),
    )

    reauthorize(request, user_id)

    return respond(result)


@router.get("/{run_id}/events")
def events(
    run_id: str,
    request: Request,
    user_id: int = Depends(authorize),
):
    validate_query(
        request, {"after_id", "limit"},
    )

    result = execute(
        storage.list_events,
        user_id,
        valid_id(run_id),
        after_id=number(
            request, "after_id",
            0, 0, 9007199254740991,
        ),
        limit=number(
            request, "limit", 100, 1, 100,
        ),
    )

    reauthorize(request, user_id)

    return respond(result)


@router.post("/{run_id}/cancel")
async def cancel(
    run_id: str,
    request: Request,
    user_id: int = Depends(authorize),
):
    no_query(request)

    identifier = valid_id(run_id)

    payload = await read_payload(
        request, WorkflowCancel, BODY_LIMIT,
    )

    def operation():
        reauthorize(request, user_id)

        result = execute(
            storage.cancel_workflow,
            user_id,
            identifier,
            payload.expected_revision,
        )

        reauthorize(request, user_id)

        return result

    return respond(
        await run_in_threadpool(operation)
    )


@router.post("/{run_id}/execute")
async def run_workflow(
    run_id: str,
    request: Request,
    user_id: int = Depends(authorize),
):
    no_query(request)

    identifier = valid_id(run_id)

    # Execution accepts no caller-provided capability,
    # handler, payload, permission or destination.
    async for chunk in request.stream():
        if chunk:
            deny(422, "Unexpected execution body")

    def operation():
        reauthorize(request, user_id)

        # Share the existing matching resource ceiling.
        if not MATCH_SLOT.acquire(blocking=False):
            deny(429, "Career operation busy")

        try:
            result = execute(
                execute_workflow,
                user_id,
                identifier,
                reauthorize=lambda: reauthorize(
                    request, user_id,
                ),
                handlers=HANDLERS,
            )

            reauthorize(request, user_id)

            return result

        finally:
            MATCH_SLOT.release()

    return respond(
        await run_in_threadpool(operation)
    )
