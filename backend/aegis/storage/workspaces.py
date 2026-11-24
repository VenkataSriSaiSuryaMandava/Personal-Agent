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
    payload = json.loads(row["payload"])

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
