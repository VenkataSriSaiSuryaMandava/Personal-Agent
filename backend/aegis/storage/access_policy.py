"""Independent storage authorization for public operations."""

import os

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path


_authorized_path: ContextVar[Path | None] = ContextVar(
    "aegis_authorized_storage",
    default=None,
)


@contextmanager
def authorize_storage(path: Path):
    token = _authorized_path.set(path.resolve())

    try:
        yield

    finally:
        _authorized_path.reset(token)


def require_storage_access(path: Path) -> None:
    if os.getenv("AEGIS_RUNTIME_MODE") != "public":
        return

    allowed = _authorized_path.get()

    if allowed is None or path.resolve() != allowed:
        raise PermissionError(
            "Public database access denied"
        )
