import json
import sqlite3

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)

from fastapi.responses import JSONResponse

from pydantic import ValidationError

from starlette.concurrency import run_in_threadpool

from aegis.api.auth import (
    SECURITY_HEADERS,
    require_owner,
)

from aegis.schemas.settings import (
    SettingsPatchRequest,
    SettingsResetRequest,
)

from aegis.services.settings import (
    SettingsService,
    UnsupportedSetting,
)

from aegis.storage.settings import (
    SettingsConflict,
    SettingsUnavailable,
)


MAX_SETTINGS_BODY = 4096

MAX_SQLITE_INTEGER = 9_223_372_036_854_775_807

from aegis.security.request_storage import (
    public_runtime,
    request_database,
)


service = SettingsService()


def current_service():
    if public_runtime():
        return SettingsService(
            request_database(service.path),
        )

    return service


def fail(
    status: int,
    detail: str,
):

    raise HTTPException(
        status_code=status,
        detail=detail,
        headers=SECURITY_HEADERS,
    )


def authorize_settings(request: Request):

    # Reject ambiguous security headers rather than
    # relying on whichever duplicate value is selected.
    for name in (
        "authorization",
        "x-aegis-gateway-token",
        "origin",
        "content-type",
    ):
        if len(request.headers.getlist(name)) > 1:
            fail(400, "Invalid request headers")

    try:

        return require_owner(request)

    except HTTPException as exc:

        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers={
                **(exc.headers or {}),
                **SECURITY_HEADERS,
            },
        ) from None


router = APIRouter(
    prefix="/api/v1/settings",
    tags=["settings"],
    dependencies=[Depends(authorize_settings)],
)


def reject_duplicate_keys(pairs):

    result = {}

    for key, value in pairs:

        if key in result:
            raise ValueError("Duplicate JSON key")

        result[key] = value

    return result


def reject_nonfinite(value):

    raise ValueError("Invalid JSON constant")


async def read_payload(request: Request, schema):

    content_type = request.headers.get(
        "content-type", ""
    ).split(";")[0].strip().lower()

    if content_type != "application/json":
        fail(415, "Unsupported content type")

    body = bytearray()

    async for chunk in request.stream():

        if len(body) + len(chunk) > MAX_SETTINGS_BODY:
            fail(413, "Request too large")

        body.extend(chunk)

    try:

        data = json.loads(
            body.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite,
        )

        return schema.model_validate(data)

    except (
        ValueError,
        UnicodeError,
        RecursionError,
    ):

        fail(422, "Invalid request")


def respond(result):

    return JSONResponse(
        content=result.model_dump(mode="json"),
        headers=SECURITY_HEADERS,
    )


def execute(operation, *args, mutation=False):

    try:

        return respond(operation(*args))

    except SettingsConflict:

        fail(
            409,
            "Settings changed; reload before saving",
        )

    except UnsupportedSetting:

        fail(
            422,
            "Setting is not currently editable",
        )

    except ValidationError:

        if mutation:
            fail(422, "Invalid settings")

        fail(503, "Settings unavailable")

    except (
        SettingsUnavailable,
        sqlite3.Error,
        OSError,
    ):

        fail(503, "Settings unavailable")


@router.get("")
def get_settings():

    return execute(current_service().get)


@router.patch("")
async def patch_settings(request: Request):

    payload = await read_payload(
        request,
        SettingsPatchRequest,
    )

    return await run_in_threadpool(
        execute,
        current_service().update,
        payload.changes,
        payload.expected_revision,
        mutation=True,
    )


@router.post("/reset")
async def reset_settings(request: Request):

    payload = await read_payload(
        request,
        SettingsResetRequest,
    )

    return await run_in_threadpool(
        execute,
        current_service().reset,
        payload.expected_revision,
        mutation=True,
    )


@router.get("/providers")
def get_providers():

    return execute(current_service().providers)


@router.get("/audit")
def get_audit(request: Request):

    params = request.query_params

    if not set(params.keys()).issubset({
        "limit", "before_id"
    }):
        fail(422, "Invalid audit query")

    if (
        len(params.getlist("limit")) > 1
        or len(params.getlist("before_id")) > 1
    ):
        fail(422, "Invalid audit query")

    def positive_integer(value, maximum):

        if not (
            value.isascii()
            and value.isdecimal()
            and 1 <= len(value) <= 19
        ):
            fail(422, "Invalid audit query")

        number = int(value)

        if not 1 <= number <= maximum:
            fail(422, "Invalid audit query")

        return number

    limit = positive_integer(
        params.get("limit", "25"),
        100,
    )

    cursor = params.get("before_id")

    before_id = (
        positive_integer(cursor, MAX_SQLITE_INTEGER)
        if cursor is not None
        else None
    )

    return execute(
        current_service().audit,
        limit,
        before_id,
    )


@router.get("/storage")
def get_storage():

    return execute(current_service().storage)
