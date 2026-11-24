"""Authenticated local conversation history."""

import json
import sqlite3

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from aegis.api import auth
from aegis.api.auth import deny, SECURITY_HEADERS

from aegis.storage.conversations import (
    ConversationNotFound,
    get_conversation,
    list_conversations,
    rename_conversation,
    delete_conversation,
)

from aegis.storage.settings import SettingsUnavailable


router = APIRouter(
    prefix="/api/v1/conversations",
    tags=["conversation history"],
)


class RenameRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    title: str = Field(
        min_length=1,
        max_length=120,
    )


def authorize(request: Request) -> int:
    for name in (
        "authorization",
        "x-aegis-gateway-token",
        "origin",
        "content-type",
    ):
        if len(request.headers.getlist(name)) > 1:
            deny(400, "Invalid request headers")

    return auth.require_owner(request)


def valid_id(value):
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError):
        deny(422, "Invalid conversation ID")

    return value


def respond(payload):
    return JSONResponse(
        content=payload,
        headers=SECURITY_HEADERS,
    )


def execute(operation, *args):
    try:
        return operation(
            *args,
            path=auth.service.path,
        )

    except ConversationNotFound:
        deny(404, "Conversation not found")

    except ValidationError:
        deny(503, "Conversation storage unavailable")

    except ValueError:
        deny(422, "Invalid conversation request")

    except (
        SettingsUnavailable,
        sqlite3.Error,
        OSError,
    ):
        deny(503, "Conversation storage unavailable")


def unique_object(items):
    result = {}

    for key, value in items:
        if key in result:
            raise ValueError("Duplicate key")

        result[key] = value

    return result


async def read_rename(request):
    media = request.headers.get(
        "content-type", ""
    ).split(";")[0].strip().lower()

    if media != "application/json":
        deny(415, "JSON required")

    raw = bytearray()

    async for chunk in request.stream():
        if len(raw) + len(chunk) > 4096:
            deny(413, "Request too large")

        raw.extend(chunk)

    try:
        payload = RenameRequest.model_validate(
            json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=unique_object,
            )
        )

        return payload

    except (
        ValueError,
        UnicodeError,
        RecursionError,
    ):
        deny(422, "Invalid conversation title")


@router.get("")
def history(
    request: Request,
    user_id: int = Depends(authorize),
):
    params = request.query_params

    if not set(params.keys()).issubset({
        "limit", "offset"
    }):
        deny(422, "Invalid history query")

    def number(name, default, minimum, maximum):
        if len(params.getlist(name)) > 1:
            deny(422, "Invalid history query")

        value = params.get(name, default)

        if not (
            value.isascii()
            and value.isdecimal()
            and len(value) <= 10
        ):
            deny(422, "Invalid history query")

        result = int(value)

        if not minimum <= result <= maximum:
            deny(422, "Invalid history query")

        return result

    limit = number("limit", "100", 1, 100)
    offset = number("offset", "0", 0, 1000000)

    records = execute(
        list_conversations,
        user_id,
        limit,
        offset,
    )

    return respond({
        "conversations": records,
        "next_offset": (
            offset + limit
            if len(records) == limit
            else None
        ),
    })


@router.get("/{conversation_id}")
def retrieve(
    conversation_id: str,
    user_id: int = Depends(authorize),
):
    result = execute(
        get_conversation,
        user_id,
        valid_id(conversation_id),
    )

    return respond(result)


@router.patch("/{conversation_id}")
async def rename(
    conversation_id: str,
    request: Request,
    user_id: int = Depends(authorize),
):
    identifier = valid_id(conversation_id)

    payload = await read_rename(request)

    result = await run_in_threadpool(
        execute,
        rename_conversation,
        user_id,
        identifier,
        payload.title,
    )

    return respond(result)


@router.delete("/{conversation_id}")
def remove(
    conversation_id: str,
    user_id: int = Depends(authorize),
):
    execute(
        delete_conversation,
        user_id,
        valid_id(conversation_id),
    )

    return respond({"deleted": True})
