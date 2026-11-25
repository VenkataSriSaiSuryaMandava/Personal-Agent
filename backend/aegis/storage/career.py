"""Owner-scoped career storage and transactional audit."""

import hashlib
import time
from uuid import uuid4

from aegis.schemas.career import (
    CareerProfile,
    ResumeMetadata,
    MAX_REVISION,
    MAX_DOCUMENT_BYTES,
    MAX_RESUME_VERSIONS,
    MAX_EXTRACTED_TEXT,
    clean_text,
)

from aegis.storage.database import DATABASE_PATH, connect
from aegis.services.resume_parser import parse_resume


class CareerNotFound(Exception):
    pass


class CareerConflict(Exception):
    pass


def audit(c, user_id, kind, identifier, event):
    c.execute("""
        INSERT INTO career_audit_events (
            user_id, entity_type, entity_id,
            event_type, created_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        user_id, kind, identifier,
        event, int(time.time()),
    ))


def get_profile(user_id, path=DATABASE_PATH):
    with connect(path) as c:
        row = c.execute("""
            SELECT payload, revision, updated_at
            FROM career_profiles
            WHERE user_id = ?
        """, (user_id,)).fetchone()

    if row is None:
        return {
            "profile": CareerProfile().model_dump(),
            "revision": 0,
            "updated_at": None,
        }

    return {
        "profile": CareerProfile.model_validate_json(
            row["payload"]
        ).model_dump(),
        "revision": row["revision"],
        "updated_at": row["updated_at"],
    }


def save_profile(
    user_id, profile, expected_revision,
    path=DATABASE_PATH,
):
    profile = CareerProfile.model_validate(
        profile.model_dump()
    )

    if (
        type(expected_revision) is not int
        or not 0 <= expected_revision < MAX_REVISION
    ):
        raise ValueError("Invalid revision")

    payload = profile.model_dump_json()

    with connect(path) as c:
        c.execute("BEGIN IMMEDIATE")

        row = c.execute("""
            SELECT revision, updated_at, payload
            FROM career_profiles
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        revision = row["revision"] if row else 0

        if revision != expected_revision:
            raise CareerConflict()

        if row and row["payload"] == payload:
            return {
                "profile": profile.model_dump(),
                "revision": revision,
                "updated_at": row["updated_at"],
            }

        now = max(
            int(time.time()),
            row["updated_at"] if row else 0,
        )

        c.execute("""
            INSERT INTO career_profiles (
                user_id, payload, revision,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                payload = excluded.payload,
                revision = excluded.revision,
                updated_at = excluded.updated_at
        """, (
            user_id, payload, revision + 1,
            now, now,
        ))

        audit(
            c, user_id, "profile", str(user_id),
            "updated" if row else "created",
        )

    return {
        "profile": profile.model_dump(),
        "revision": revision + 1,
        "updated_at": now,
    }


RESUME_COLUMNS = """
    id, title, media_type, size_bytes, sha256,
    is_active, revision, created_at, updated_at
"""


def list_resumes(user_id, path=DATABASE_PATH):
    with connect(path) as c:
        rows = c.execute("""
            SELECT
                id, title, media_type, size_bytes, sha256,
                is_active, revision, created_at, updated_at
            FROM resume_versions
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
        """, (user_id,)).fetchall()

        return [dict(row) for row in rows]


def get_resume(user_id, identifier, path=DATABASE_PATH):
    with connect(path) as c:
        row = c.execute("""
            SELECT
                id, title, media_type, size_bytes, sha256,
                is_active, revision, created_at, updated_at,
                extracted_text
            FROM resume_versions
            WHERE user_id = ? AND id = ?
        """, (user_id, identifier)).fetchone()

        if row is None:
            raise CareerNotFound()

        return dict(row)


def check_upload(c, user_id, digest):
    count = c.execute("""
        SELECT COUNT(*) FROM resume_versions
        WHERE user_id = ?
    """, (user_id,)).fetchone()[0]

    if count >= MAX_RESUME_VERSIONS:
        raise CareerConflict("Resume limit reached")

    if c.execute("""
        SELECT 1 FROM resume_versions
        WHERE user_id = ? AND sha256 = ?
    """, (user_id, digest)).fetchone():
        raise CareerConflict("Duplicate document")

    return count


def create_resume(
    user_id, metadata, data,
    path=DATABASE_PATH,
    *,
    before_write=None,
):
    metadata = ResumeMetadata.model_validate(
        metadata.model_dump()
    )

    if (
        not isinstance(data, bytes)
        or not 1 <= len(data) <= MAX_DOCUMENT_BYTES
    ):
        raise ValueError("Invalid document size")

    digest = hashlib.sha256(data).hexdigest()

    with connect(path) as c:
        check_upload(c, user_id, digest)

    extracted = parse_resume(
        data, metadata.media_type
    )

    if before_write is not None:
        before_write()

    identifier = str(uuid4())
    now = int(time.time())

    with connect(path) as c:
        c.execute("BEGIN IMMEDIATE")

        count = check_upload(c, user_id, digest)

        c.execute("""
            INSERT INTO resume_versions (
                id, user_id, title, media_type,
                document, size_bytes, sha256,
                extracted_text, is_active,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            identifier, user_id,
            metadata.title, metadata.media_type,
            data, len(data), digest, extracted,
            int(count == 0), now, now,
        ))

        audit(
            c, user_id, "resume", identifier, "created"
        )

    return get_resume(user_id, identifier, path)


def download_resume(
    user_id, identifier, path=DATABASE_PATH,
):
    with connect(path) as c:
        row = c.execute("""
            SELECT document, media_type, sha256
            FROM resume_versions
            WHERE user_id = ? AND id = ?
        """, (user_id, identifier)).fetchone()

        if row is None:
            raise CareerNotFound()

        if hashlib.sha256(
            row["document"]
        ).hexdigest() != row["sha256"]:
            raise RuntimeError("Document integrity failure")

        return row["document"], row["media_type"]


def require_revision(row, expected_revision):
    if expected_revision is not None and (
        type(expected_revision) is not int
        or row["revision"] != expected_revision
    ):
        raise CareerConflict("Resume changed")


def activate_resume(
    user_id, identifier, path=DATABASE_PATH,
    *, expected_revision=None,
):
    with connect(path) as c:
        c.execute("BEGIN IMMEDIATE")

        row = c.execute("""
            SELECT is_active, revision FROM resume_versions
            WHERE user_id = ? AND id = ?
        """, (user_id, identifier)).fetchone()

        if row is None:
            raise CareerNotFound()

        require_revision(row, expected_revision)

        if not row["is_active"]:
            now = int(time.time())

            c.execute("""
                UPDATE resume_versions
                SET is_active = 0, updated_at = ?, revision = revision + 1
                WHERE user_id = ? AND is_active = 1
            """, (now, user_id))

            c.execute("""
                UPDATE resume_versions
                SET is_active = 1, updated_at = ?, revision = revision + 1
                WHERE user_id = ? AND id = ?
            """, (now, user_id, identifier))

            audit(
                c, user_id, "resume",
                identifier, "activated",
            )

    return get_resume(user_id, identifier, path)


def update_resume_text(
    user_id, identifier, text, path=DATABASE_PATH,
    *, expected_revision=None,
):
    text = clean_text(text)

    if len(text) > MAX_EXTRACTED_TEXT:
        raise ValueError("Resume text too large")

    with connect(path) as c:
        c.execute("BEGIN IMMEDIATE")

        row = c.execute("""
            SELECT extracted_text, revision
            FROM resume_versions
            WHERE user_id = ? AND id = ?
        """, (user_id, identifier)).fetchone()

        if row is None:
            raise CareerNotFound()

        require_revision(row, expected_revision)

        if row["extracted_text"] != text:
            c.execute("""
                UPDATE resume_versions
                SET extracted_text = ?, updated_at = ?, revision = revision + 1
                WHERE user_id = ? AND id = ?
            """, (
                text, int(time.time()),
                user_id, identifier,
            ))

            audit(
                c, user_id, "resume",
                identifier, "updated",
            )

    return get_resume(user_id, identifier, path)


def delete_resume(
    user_id, identifier, path=DATABASE_PATH,
    *, expected_revision=None,
):
    with connect(path) as c:
        c.execute("BEGIN IMMEDIATE")

        row = c.execute("""
            SELECT revision FROM resume_versions
            WHERE user_id = ? AND id = ?
        """, (user_id, identifier)).fetchone()

        if row is None:
            raise CareerNotFound()

        require_revision(row, expected_revision)

        result = c.execute("""
            DELETE FROM resume_versions
            WHERE user_id = ? AND id = ?
        """, (user_id, identifier))

        if result.rowcount != 1:
            raise CareerNotFound()

        audit(
            c, user_id, "resume",
            identifier, "deleted",
        )

    return {"deleted": True}
