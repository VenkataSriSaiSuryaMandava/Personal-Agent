import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from aegis.api.auth import require_owner, deny, SECURITY_HEADERS
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

router = APIRouter(prefix="/api/v1")
MAX_BODY = 98304


def unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate key")
        result[key] = value
    return result


@router.post("/conversation", dependencies=[Depends(require_owner)])
async def conversation(request: Request):
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
    return JSONResponse(content=result.model_dump(), headers=SECURITY_HEADERS)
