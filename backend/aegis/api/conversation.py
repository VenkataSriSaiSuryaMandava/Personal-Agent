import json
import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from aegis.api.auth import deny, SECURITY_HEADERS
from aegis.schemas.conversation import ConversationRequest
from aegis.security.gateway import (
    GatewayDenied,
    ProviderUnavailable,
    ProviderQuotaExceeded,
    ProviderTimedOut,
    ProviderTemporarilyUnavailable,
)
from aegis.security.rate_limit import RateLimitExceeded, UsageStorageUnavailable
from aegis.services.conversation import run_conversation

from aegis.api import auth

from aegis.api.conversation_history import authorize

from aegis.storage.conversations import (
    ConversationNotFound,
    ConversationConflict,
    RetentionDisabled,
    get_conversation,
    save_turn,
)

from aegis.storage.settings import (
    SettingsUnavailable,
    load_settings,
)


router = APIRouter(prefix="/api/v1")
MAX_BODY = 98304


def unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate key")
        result[key] = value
    return result


@router.post("/conversation")
async def conversation(
    request: Request,
    user_id: int = Depends(authorize),
):
    media = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media != "application/json":
        deny(415, "JSON required")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_BODY:
            deny(413, "Request too large")
        raw.extend(chunk)
    try:
        payload = ConversationRequest.model_validate(
            json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
        )
    except (ValueError, ValidationError, UnicodeError, RecursionError):
        deny(422, "Invalid conversation")
    should_persist = False

    if payload.persist:
        try:
            snapshot = await run_in_threadpool(
                load_settings,
                auth.service.path,
            )

            should_persist = (
                snapshot.settings.retain_conversations
            )

            if payload.conversation_id is not None:
                saved = await run_in_threadpool(
                    get_conversation,
                    user_id,
                    payload.conversation_id,
                    auth.service.path,
                )

                if len(saved["turns"]) != payload.expected_turn_count:
                    deny(409, "Conversation changed; reload")

                if not should_persist:
                    deny(409, "Conversation retention is disabled")

        except ConversationNotFound:
            deny(404, "Conversation not found")

        except (
            SettingsUnavailable,
            sqlite3.Error,
            OSError,
            ValidationError,
        ):
            deny(503, "Conversation storage unavailable")

    try:
        result = await run_in_threadpool(run_conversation, payload)
    except GatewayDenied:
        deny(403, "Conversation denied by policy")
    except RateLimitExceeded:
        deny(429, "Inference usage limit reached")
    except ProviderQuotaExceeded:
        deny(429, "Provider quota exceeded")
    except ProviderTimedOut:
        deny(504, "Provider request timed out")
    except ProviderTemporarilyUnavailable:
        deny(503, "Provider temporarily unavailable")
    except UsageStorageUnavailable:
        deny(503, "Usage storage unavailable")
    except ProviderUnavailable:
        deny(503, "AI unavailable")
    response = result.model_dump()

    if payload.persist:
        response["persisted"] = False
        response["conversation_id"] = None
        response["persistence_status"] = "retention_disabled"

        if should_persist:
            try:
                # Recheck authentication before retaining
                # content after a potentially long AI request.
                await run_in_threadpool(
                    authorize,
                    request,
                )

                identifier = await run_in_threadpool(
                    save_turn,
                    user_id,
                    payload.message,
                    result.message,
                    payload.conversation_id,
                    payload.expected_turn_count,
                    auth.service.path,
                )

                response["persisted"] = True
                response["conversation_id"] = identifier
                response["persistence_status"] = "saved"

            except RetentionDisabled:
                response["persistence_status"] = (
                    "retention_disabled"
                )

            except (
                ConversationConflict,
                ConversationNotFound,
            ):
                response["persistence_status"] = (
                    "conversation_changed"
                )

            except (
                SettingsUnavailable,
                sqlite3.Error,
                OSError,
                ValidationError,
                ValueError,
            ):
                response["persistence_status"] = (
                    "storage_unavailable"
                )

    return JSONResponse(
        content=response,
        headers=SECURITY_HEADERS,
    )
