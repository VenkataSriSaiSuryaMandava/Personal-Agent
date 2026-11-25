"""Request-local storage selection.

Public requests must have an isolated database context.
They must never fall back to the private database.
"""

import os

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from fastapi import HTTPException

from aegis.storage.access_policy import authorize_storage


_request_database: ContextVar[Path | None] = ContextVar(
    "aegis_request_database",
    default=None,
)


def public_runtime() -> bool:
    return os.getenv("AEGIS_RUNTIME_MODE") == "public"


@contextmanager
def database_context(path: Path):
    if not isinstance(path, Path):
        raise TypeError("Database path required")

    token = _request_database.set(path)

    try:
        with authorize_storage(path):
            yield

    finally:
        _request_database.reset(token)


def request_database(private_path: Path) -> Path:
    path = _request_database.get()

    if public_runtime():
        if path is None:
            raise HTTPException(
                status_code=401,
                detail="Public session required",
                headers={"Cache-Control": "no-store"},
            )

        return path

    return private_path
