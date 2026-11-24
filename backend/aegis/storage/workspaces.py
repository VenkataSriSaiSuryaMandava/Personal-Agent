import json
import time

from pathlib import Path
from uuid import uuid4

from aegis.schemas.workspaces import (
    STATUSES,
    WorkspaceRecord,
    validate_record,
)

from aegis.storage.database import (
    DATABASE_PATH,
    connect,
)


class RecordNotFound(Exception):
    pass


class RecordConflict(Exception):
    pass


def serialize(row):
    payload = WorkspaceRecord.model_validate(
        json.loads(row["payload"])
    ).model_dump()

    return {
        **payload,
        "id": row["id"],
        "workspace": row["workspace"],
        "revision": row["revision"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_records(
    user_id: int,
    workspace: str,
    limit: int = 100,
    offset: int = 0,
    path: Path = DATABASE_PATH,
):
    if workspace not in STATUSES:
        raise ValueError("Invalid workspace")

    if not 1 <= limit <= 100:
        raise ValueError("Invalid limit")

    if not 0 <= offset <= 1000000:
        raise ValueError("Invalid offset")

    with connect(path) as connection:
        rows = connection.execute("""
            SELECT *
            FROM workspace_records
            WHERE user_id = ? AND workspace = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT ? OFFSET ?
        """, (
            user_id,
            workspace,
            limit,
            offset,
        )).fetchall()

    return [serialize(row) for row in rows]


def list_page(
    user_id: int,
    workspace: str,
    limit: int = 100,
    offset: int = 0,
    path: Path = DATABASE_PATH,
):
    if workspace not in STATUSES:
        raise ValueError("Invalid workspace")

    if not 1 <= limit <= 100:
        raise ValueError("Invalid limit")

    if not 0 <= offset <= 1000000:
        raise ValueError("Invalid offset")

    with connect(path) as connection:
        rows = connection.execute("""
            SELECT *
            FROM workspace_records
            WHERE user_id = ? AND workspace = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT ? OFFSET ?
        """, (
            user_id,
            workspace,
            limit + 1,
            offset,
        )).fetchall()

    return {
        "records": [
            serialize(row)
            for row in rows[:limit]
        ],
        "next_offset": (
            offset + limit
            if len(rows) > limit
            and offset + limit <= 1000000
            else None
        ),
    }


def list_audit_events(
    user_id: int,
    limit: int = 100,
    path: Path = DATABASE_PATH,
):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid audit limit")

    with connect(path) as connection:
        rows = connection.execute("""
            SELECT id, workspace, record_id,
                   event_type, revision, created_at
            FROM workspace_audit_events
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()

    return [dict(row) for row in rows]


def counts(
    user_id: int,
    path: Path = DATABASE_PATH,
):
    result = {
        workspace: 0
        for workspace in STATUSES
    }

    with connect(path) as connection:
        rows = connection.execute("""
            SELECT workspace, COUNT(*) AS total
            FROM workspace_records
            WHERE user_id = ?
            GROUP BY workspace
        """, (user_id,)).fetchall()

    for row in rows:
        result[row["workspace"]] = row["total"]

    return result


def create_record(
    user_id: int,
    workspace: str,
    record: WorkspaceRecord,
    path: Path = DATABASE_PATH,
):
    record = validate_record(
        workspace, record
    )

    identifier = str(uuid4())
    now = int(time.time())

    with connect(path) as connection:
        connection.execute("""
            INSERT INTO workspace_records (
                id, user_id, workspace, payload,
                revision, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 1, ?, ?)
        """, (
            identifier,
            user_id,
            workspace,
            record.model_dump_json(),
            now,
            now,
        ))

    return {
        **record.model_dump(),
        "id": identifier,
        "workspace": workspace,
        "revision": 1,
        "created_at": now,
        "updated_at": now,
    }


def update_record(
    user_id: int,
    workspace: str,
    identifier: str,
    record: WorkspaceRecord,
    expected_revision: int,
    path: Path = DATABASE_PATH,
):
    record = validate_record(
        workspace, record
    )

    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute("""
            SELECT *
            FROM workspace_records
            WHERE user_id = ?
                AND workspace = ?
                AND id = ?
        """, (
            user_id,
            workspace,
            identifier,
        )).fetchone()

        if row is None:
            raise RecordNotFound()

        if row["revision"] != expected_revision:
            raise RecordConflict()

        now = max(
            int(time.time()),
            row["updated_at"],
        )

        if expected_revision >= 9007199254740991:
            raise RecordConflict()

        revision = expected_revision + 1

        connection.execute("""
            UPDATE workspace_records
            SET payload = ?,
                revision = ?,
                updated_at = ?
            WHERE user_id = ?
                AND workspace = ?
                AND id = ?
        """, (
            record.model_dump_json(),
            revision,
            now,
            user_id,
            workspace,
            identifier,
        ))

        return {
            **record.model_dump(),
            "id": identifier,
            "workspace": workspace,
            "revision": revision,
            "created_at": row["created_at"],
            "updated_at": now,
        }


def delete_record(
    user_id: int,
    workspace: str,
    identifier: str,
    expected_revision: int,
    path: Path = DATABASE_PATH,
):
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute("""
            SELECT revision
            FROM workspace_records
            WHERE user_id = ?
                AND workspace = ?
                AND id = ?
        """, (
            user_id,
            workspace,
            identifier,
        )).fetchone()

        if row is None:
            raise RecordNotFound()

        if row["revision"] != expected_revision:
            raise RecordConflict()

        connection.execute("""
            DELETE FROM workspace_records
            WHERE user_id = ?
                AND workspace = ?
                AND id = ?
        """, (
            user_id,
            workspace,
            identifier,
        ))

    return {"deleted": True}


def workspace_summary(
    user_id: int,
    path: Path = DATABASE_PATH,
):
    totals = {
        workspace: 0 for workspace in STATUSES
    }

    statuses = {
        workspace: {
            status: 0 for status in values
        }
        for workspace, values in STATUSES.items()
    }

    with connect(path) as connection:
        connection.execute("BEGIN")

        rows = connection.execute("""
            SELECT workspace,
                   json_extract(payload, '$.status') AS status,
                   COUNT(*) AS total
            FROM workspace_records
            WHERE user_id = ?
            GROUP BY workspace, status
        """, (user_id,)).fetchall()

        for row in rows:
            workspace = row["workspace"]
            status = row["status"]

            if status not in statuses[workspace]:
                raise ValueError("Invalid stored status")

            totals[workspace] += row["total"]
            statuses[workspace][status] = row["total"]

        memory_bytes = connection.execute("""
            SELECT COALESCE(
                SUM(length(CAST(payload AS BLOB))), 0
            )
            FROM workspace_records
            WHERE user_id = ?
            AND workspace = 'memory'
        """, (user_id,)).fetchone()[0]

        conversations = connection.execute("""
            SELECT COUNT(*)
            FROM conversations
            WHERE user_id = ?
        """, (user_id,)).fetchone()[0]

        page_count = connection.execute(
            "PRAGMA page_count"
        ).fetchone()[0]

        page_size = connection.execute(
            "PRAGMA page_size"
        ).fetchone()[0]

    return {
        "counts": totals,
        "statuses": statuses,
        "storage": {
            "memory_payload_bytes": memory_bytes,
            "conversation_count": conversations,
            "database_page_bytes": page_count * page_size,
        },
    }
