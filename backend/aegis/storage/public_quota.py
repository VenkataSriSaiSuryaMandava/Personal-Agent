"""Physical SQLite allocation limits for public visitor databases."""

import os

from pathlib import Path


PUBLIC_DATABASE_LIMIT = 64 * 1024 * 1024


def apply_public_quota(connection, path: Path) -> None:
    if os.getenv("AEGIS_RUNTIME_MODE") != "public":
        return

    page_size = connection.execute(
        "PRAGMA page_size"
    ).fetchone()[0]

    if not 512 <= page_size <= 65536:
        raise RuntimeError("Invalid database page size")

    max_pages = PUBLIC_DATABASE_LIMIT // page_size

    current_pages = connection.execute(
        "PRAGMA page_count"
    ).fetchone()[0]

    if current_pages > max_pages:
        raise OSError("Public database quota exceeded")

    # max_page_count must be enforced on each connection.
    actual = connection.execute(
        f"PRAGMA max_page_count = {max_pages:d}"
    ).fetchone()[0]

    if actual != max_pages:
        raise OSError("Public database quota unavailable")
