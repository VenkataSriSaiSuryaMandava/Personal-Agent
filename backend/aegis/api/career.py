"""Private career profile and resume endpoints."""

import base64
import binascii
import json
import sqlite3

from threading import BoundedSemaphore
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from pydantic import (
    BaseModel, ConfigDict, Field, ValidationError,
    model_validator,
)

from starlette.concurrency import run_in_threadpool

from aegis.api import auth
from aegis.security.request_storage import request_database
from aegis.api.auth import deny, SECURITY_HEADERS

from aegis.api.conversation_history import (
    authorize, respond, unique_object, valid_id,
)

from aegis.schemas.career import (
    CareerProfile,
    CareerProfileUpdate,
    ResumeMetadata,
    ResumeTextUpdate,
    MAX_DOCUMENT_BYTES,
    MAX_REVISION,
)

from aegis.services.resume_parser import (
    DocumentRejected, ParserBusy,
)

from aegis.storage import career as storage

router = APIRouter(
    prefix="/api/v1/career",
    tags=["private career"],
)

JSON_LIMIT = 2 * 1024 * 1024
UPLOAD_LIMIT = 14 * 1024 * 1024
UPLOAD_SLOT = BoundedSemaphore(1)

EXTENSIONS = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
}


class ResumeUpload(ResumeMetadata):
    document: str = Field(
        min_length=4,
        max_length=4 * ((MAX_DOCUMENT_BYTES + 2) // 3),
    )


class ResumeAction(BaseModel):
    model_config = ConfigDict(
        strict=True, extra="forbid",
    )

    id: str = Field(min_length=36, max_length=36)
    action: Literal["activate", "edit", "delete"]

    expected_revision: int = Field(
        ge=1, le=MAX_REVISION,
    )

    extracted_text: str | None = Field(
        default=None, max_length=100000,
    )

    @model_validator(mode="after")
    def validate_action(self):
        if self.action == "edit":
            if self.extracted_text is None:
                raise ValueError("Text required")

            ResumeTextUpdate(
                extracted_text=self.extracted_text,
            )
        elif self.extracted_text is not None:
            raise ValueError("Unexpected text")

        return self


def execute(operation, *args, **kwargs):
    try:
        return operation(
            *args,
            path=request_database(auth.service.path),
            **kwargs,
        )
    except storage.CareerNotFound:
        deny(404, "Career record not found")
    except storage.CareerConflict:
        deny(409, "Conflict or resume limit reached")
    except ParserBusy:
        deny(429, "Document parser busy")
    except DocumentRejected:
        deny(422, "Invalid or unsupported document")
    except ValidationError:
        deny(503, "Career storage unavailable")
    except ValueError:
        deny(422, "Invalid career request")
    except (sqlite3.Error, OSError, RuntimeError):
        deny(503, "Career storage unavailable")


def no_query(request):
    if request.query_params:
        deny(422, "Invalid query")


def resume_id(request):
    params = list(request.query_params.multi_items())

    if len(params) != 1 or params[0][0] != "id":
        deny(422, "Invalid query")

    return valid_id(params[0][1])


def reauthorize(request, user_id):
    if authorize(request) != user_id:
        deny(403, "Request denied")


async def read_payload(request, schema, limit):
    media = request.headers.get(
        "content-type", "",
    ).split(";")[0].strip().lower()

    if media != "application/json":
        deny(415, "JSON required")

    if request.headers.get("content-encoding"):
        deny(415, "Unsupported content encoding")

    raw = bytearray()

    async for chunk in request.stream():
        if len(raw) + len(chunk) > limit:
            deny(413, "Request too large")

        raw.extend(chunk)

    try:
        return schema.model_validate(
            json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=unique_object,
            )
        )
    except (ValueError, UnicodeError, RecursionError):
        deny(422, "Invalid career request")


@router.get("/profile")
def profile(
    request: Request,
    user_id: int = Depends(authorize),
):
    no_query(request)
    return respond(execute(storage.get_profile, user_id))


@router.patch("/profile")
async def update_profile(
    request: Request,
    user_id: int = Depends(authorize),
):
    no_query(request)

    payload = await read_payload(
        request, CareerProfileUpdate, JSON_LIMIT,
    )

    record = CareerProfile.model_validate(
        payload.model_dump(
            exclude={"expected_revision"},
        )
    )

    await run_in_threadpool(
        reauthorize, request, user_id,
    )

    return respond(await run_in_threadpool(
        execute,
        storage.save_profile,
        user_id,
        record,
        payload.expected_revision,
    ))


@router.get("/resumes")
def resumes(
    request: Request,
    user_id: int = Depends(authorize),
):
    no_query(request)

    return respond({
        "resumes": execute(
            storage.list_resumes, user_id,
        ),
    })


@router.post("/resumes")
async def upload(
    request: Request,
    user_id: int = Depends(authorize),
):
    no_query(request)

    if not UPLOAD_SLOT.acquire(blocking=False):
        deny(429, "Document upload busy")

    try:
        payload = await read_payload(
            request, ResumeUpload, UPLOAD_LIMIT,
        )

        try:
            document = base64.b64decode(
                payload.document, validate=True,
            )
        except (ValueError, binascii.Error):
            deny(422, "Invalid document encoding")

        if not 1 <= len(document) <= MAX_DOCUMENT_BYTES:
            deny(413, "Invalid document size")

        metadata = ResumeMetadata(
            title=payload.title,
            media_type=payload.media_type,
        )

        await run_in_threadpool(
            reauthorize, request, user_id,
        )

        return respond(await run_in_threadpool(
            execute,
            storage.create_resume,
            user_id,
            metadata,
            document,
            before_write=lambda: reauthorize(
                request, user_id,
            ),
        ))

    finally:
        UPLOAD_SLOT.release()


@router.get("/resume")
def resume(
    request: Request,
    user_id: int = Depends(authorize),
):
    identifier = resume_id(request)

    return respond(execute(
        storage.get_resume,
        user_id,
        identifier,
    ))


@router.post("/resume")
async def mutate_resume(
    request: Request,
    user_id: int = Depends(authorize),
):
    no_query(request)

    payload = await read_payload(
        request, ResumeAction, JSON_LIMIT,
    )

    identifier = valid_id(payload.id)

    await run_in_threadpool(
        reauthorize, request, user_id,
    )

    operations = {
        "activate": storage.activate_resume,
        "edit": storage.update_resume_text,
        "delete": storage.delete_resume,
    }

    args = [user_id, identifier]

    if payload.action == "edit":
        args.append(payload.extracted_text)

    return respond(await run_in_threadpool(
        execute,
        operations[payload.action],
        *args,
        expected_revision=payload.expected_revision,
    ))


@router.get("/download")
def download(
    request: Request,
    user_id: int = Depends(authorize),
):
    identifier = resume_id(request)

    document, media = execute(
        storage.download_resume,
        user_id,
        identifier,
    )

    extension = EXTENSIONS.get(media)

    if extension is None:
        deny(503, "Document unavailable")

    return Response(
        content=document,
        media_type="application/octet-stream",
        headers={
            **SECURITY_HEADERS,
            "Content-Disposition":
                f'attachment; filename="resume.{extension}"',
        },
    )
