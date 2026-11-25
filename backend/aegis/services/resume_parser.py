"""Bounded local document parsing; no cloud inference."""

import json
import subprocess
import sys
from threading import BoundedSemaphore

from aegis.schemas.career import (
    MAX_DOCUMENT_BYTES,
    MAX_EXTRACTED_TEXT,
    clean_text,
)

MEDIA_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}

PARSER_SLOT = BoundedSemaphore(1)


class DocumentRejected(ValueError):
    pass


class ParserBusy(RuntimeError):
    pass


def parse_resume(data: bytes, media_type: str) -> str:
    if (
        not isinstance(data, bytes)
        or not 1 <= len(data) <= MAX_DOCUMENT_BYTES
        or media_type not in MEDIA_TYPES
    ):
        raise DocumentRejected("Invalid document")

    if not PARSER_SLOT.acquire(blocking=False):
        raise ParserBusy("Document parser busy")

    try:
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-m",
                    "aegis.services.resume_worker",
                    media_type,
                ],
                input=data,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
                env={"PYTHONIOENCODING": "utf-8"},
            )

        except (subprocess.TimeoutExpired, OSError):
            raise DocumentRejected(
                "Document parsing unavailable"
            ) from None

        if (
            result.returncode != 0
            or len(result.stdout) > 1300000
        ):
            raise DocumentRejected(
                "Invalid or unsupported document"
            )

        try:
            text = json.loads(result.stdout)["text"]

            if (
                not isinstance(text, str)
                or len(text) > MAX_EXTRACTED_TEXT
            ):
                raise ValueError()

            return clean_text(text)

        except (ValueError, KeyError, TypeError):
            raise DocumentRejected(
                "Invalid extracted document"
            ) from None

    finally:
        PARSER_SLOT.release()
