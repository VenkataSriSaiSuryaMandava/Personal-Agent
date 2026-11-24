import json
import sqlite3

from pydantic import ValidationError

from fastapi import (
    APIRouter,
    Depends,
    Request,
)

from starlette.concurrency import (
    run_in_threadpool,
)

from aegis.api import auth

from aegis.api.auth import deny

from aegis.api.conversation_history import (
    authorize,
    respond,
    unique_object,
    valid_id,
)

from aegis.schemas.workspaces import (
    STATUSES,
    WorkspaceRecord,
    WorkspaceUpdate,
)

from aegis.storage import workspaces as storage


router = APIRouter(
    prefix="/api/v1/workspaces",
    tags=["local workspaces"],
)


def execute(operation, *args):
    try:
        return operation(
            *args,
            path=auth.service.path,
        )

    except storage.RecordNotFound:
        deny(404, "Workspace record not found")

    except storage.RecordConflict:
        deny(409, "Record changed; reload")

    except ValidationError:
        deny(503, "Workspace storage unavailable")

    except json.JSONDecodeError:
        deny(503, "Workspace storage unavailable")

    except ValueError:
        deny(422, "Invalid workspace request")

    except (sqlite3.Error, OSError):
        deny(503, "Workspace storage unavailable")


def check_workspace(workspace):
    if workspace not in STATUSES:
        deny(422, "Invalid workspace")


def number(request, key, default, low, high):
    query = request.query_params

    if len(query.getlist(key)) > 1:
        deny(422, "Invalid query")

    value = query.get(key, str(default))

    if (
        not value.isascii()
        or not value.isdecimal()
        or len(value) > 19
    ):
        deny(422, "Invalid query")

    result = int(value)

    if not low <= result <= high:
        deny(422, "Invalid query")

    return result


async def read_payload(request, schema):
    media = request.headers.get(
        "content-type", ""
    ).split(";")[0].strip().lower()

    if media != "application/json":
        deny(415, "JSON required")

    raw = bytearray()

    async for chunk in request.stream():
        if len(raw) + len(chunk) > 65536:
            deny(413, "Request too large")

        raw.extend(chunk)

    try:
        return schema.model_validate(
            json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=unique_object,
            )
        )
    except (
        ValueError,
        UnicodeError,
        RecursionError,
    ):
        deny(422, "Invalid workspace record")


@router.get("/summary")
def summary(
    request: Request,
    user_id: int = Depends(authorize),
):
    if request.query_params:
        deny(422, "Invalid query")

    return respond(
        execute(storage.workspace_summary, user_id)
    )


@router.get("/{workspace}")
def records(
    workspace: str,
    request: Request,
    user_id: int = Depends(authorize),
):
    check_workspace(workspace)

    if not set(request.query_params).issubset({
        "limit", "offset"
    }):
        deny(422, "Invalid query")

    limit = number(
        request, "limit", 100, 1, 100
    )

    offset = number(
        request, "offset", 0, 0, 1000000
    )

    return respond(
        execute(
            storage.list_page,
            user_id,
            workspace,
            limit,
            offset,
        )
    )


@router.post("/{workspace}")
async def create(
    workspace: str,
    request: Request,
    user_id: int = Depends(authorize),
):
    check_workspace(workspace)

    payload = await read_payload(
        request,
        WorkspaceRecord,
    )

    current_user = await run_in_threadpool(
        authorize, request
    )

    if current_user != user_id:
        deny(403, "Request denied")


    return respond(
        await run_in_threadpool(
            execute,
            storage.create_record,
            user_id,
            workspace,
            payload,
        )
    )


@router.patch("/{workspace}/{identifier}")
async def update(
    workspace: str,
    identifier: str,
    request: Request,
    user_id: int = Depends(authorize),
):
    check_workspace(workspace)
    valid_id(identifier)

    payload = await read_payload(
        request,
        WorkspaceUpdate,
    )

    current_user = await run_in_threadpool(
        authorize, request
    )

    if current_user != user_id:
        deny(403, "Request denied")


    record = WorkspaceRecord.model_validate(
        payload.model_dump(
            exclude={"expected_revision"}
        )
    )

    return respond(
        await run_in_threadpool(
            execute,
            storage.update_record,
            user_id,
            workspace,
            identifier,
            record,
            payload.expected_revision,
        )
    )


@router.delete("/{workspace}/{identifier}")
def remove(
    workspace: str,
    identifier: str,
    request: Request,
    user_id: int = Depends(authorize),
):
    check_workspace(workspace)
    valid_id(identifier)

    if set(request.query_params) != {
        "revision"
    }:
        deny(422, "Invalid query")

    revision = number(
        request,
        "revision",
        0,
        1,
        9007199254740991,
    )

    return respond(
        execute(
            storage.delete_record,
            user_id,
            workspace,
            identifier,
            revision,
        )
    )
