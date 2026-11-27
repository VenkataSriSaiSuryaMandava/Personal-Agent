"""Owner-scoped persistence for registered agent workflows."""

import json
import time
from uuid import UUID, uuid4

from aegis.schemas.workflows import (
    MAX_ACTIVE_WORKFLOWS,
    MAX_GUEST_ACTIVE_WORKFLOWS,
    MAX_WORKFLOW_PAYLOAD_BYTES,
    WorkflowCreate,
)
from aegis.security.request_storage import public_runtime
from aegis.services.agents.registry import resolve_capability
from aegis.storage.database import connect


WORKFLOW_CAPABILITIES = {
    "company_summary": "career.company_summary",
    "match_listing": "career.match_listing",
}

TERMINAL_STATES = frozenset({
    "completed", "failed", "cancelled", "uncertain",
})

MAX_RETAINED_RUNS = 1000
MAX_GUEST_RETAINED_RUNS = 50


class WorkflowNotFound(Exception):
    pass


class WorkflowConflict(Exception):
    pass


class WorkflowCapacityReached(Exception):
    pass


def canonical_id(value):
    return str(UUID(str(value)))


def encode_payload(value):
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    if len(encoded.encode("utf-8")) > MAX_WORKFLOW_PAYLOAD_BYTES:
        raise ValueError("Workflow payload too large")

    return encoded


def append_event(
    connection,
    user_id,
    run_id,
    event_type,
    step_id=None,
):
    connection.execute("""
        INSERT INTO workflow_events (
            user_id, run_id, step_id,
            event_type, created_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        user_id,
        run_id,
        step_id,
        event_type,
        int(time.time()),
    ))


def select_run(connection, user_id, run_id):
    row = connection.execute("""
        SELECT *
        FROM workflow_runs
        WHERE user_id = ? AND id = ?
    """, (
        user_id,
        canonical_id(run_id),
    )).fetchone()

    if row is None:
        raise WorkflowNotFound()

    return row


def create_workflow(user_id, request, path):
    if not isinstance(request, WorkflowCreate):
        raise ValueError("Invalid workflow request")

    capability = resolve_capability(
        WORKFLOW_CAPABILITIES[request.workflow_type]
    )

    guest = public_runtime()

    if guest and not capability.guest_allowed:
        raise ValueError("Capability unavailable")

    target = canonical_id(request.target_id)
    request_key = canonical_id(request.request_key)

    input_field = (
        "source_id"
        if request.workflow_type == "company_summary"
        else "listing_id"
    )

    validated = capability.input_model.model_validate_json(
        encode_payload({input_field: target})
    )

    payload = encode_payload(
        validated.model_dump(mode="json")
    )

    now = int(time.time())

    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        existing = connection.execute("""
            SELECT *
            FROM workflow_runs
            WHERE user_id = ?
                AND workflow_type = ?
                AND request_key = ?
        """, (
            user_id,
            request.workflow_type,
            request_key,
        )).fetchone()

        if existing is not None:
            if existing["target_id"] != target:
                raise WorkflowConflict()

            return dict(existing)

        if request.workflow_type == "company_summary":
            target_row = connection.execute("""
                SELECT id FROM job_sources
                WHERE user_id = ?
                    AND id = ?
                    AND enabled = 1
            """, (user_id, target)).fetchone()

        else:
            target_row = connection.execute("""
                SELECT id FROM job_listings
                WHERE user_id = ? AND id = ?
            """, (user_id, target)).fetchone()

        if target_row is None:
            raise WorkflowNotFound()

        active = connection.execute("""
            SELECT COUNT(*)
            FROM workflow_runs
            WHERE user_id = ?
                AND status NOT IN (
                    'completed', 'failed',
                    'cancelled', 'uncertain'
                )
        """, (user_id,)).fetchone()[0]

        active_limit = (
            MAX_GUEST_ACTIVE_WORKFLOWS
            if guest else MAX_ACTIVE_WORKFLOWS
        )

        if active >= active_limit:
            raise WorkflowCapacityReached()

        retained = connection.execute("""
            SELECT COUNT(*)
            FROM workflow_runs
            WHERE user_id = ?
        """, (user_id,)).fetchone()[0]

        retained_limit = (
            MAX_GUEST_RETAINED_RUNS
            if guest else MAX_RETAINED_RUNS
        )

        if retained >= retained_limit:
            raise WorkflowCapacityReached()

        run_id = str(uuid4())
        step_id = str(uuid4())

        connection.execute("""
            INSERT INTO workflow_runs (
                id, user_id, workflow_type,
                definition_version, request_key,
                target_id, status, created_at, updated_at
            )
            VALUES (?, ?, ?, 1, ?, ?, 'queued', ?, ?)
        """, (
            run_id,
            user_id,
            request.workflow_type,
            request_key,
            target,
            now,
            now,
        ))

        connection.execute("""
            INSERT INTO workflow_steps (
                id, user_id, run_id,
                step_key, capability, capability_version,
                status, input_payload,
                available_at, created_at, updated_at
            )
            VALUES (
                ?, ?, ?, 'initial', ?, ?,
                'queued', ?, ?, ?, ?
            )
        """, (
            step_id,
            user_id,
            run_id,
            capability.name,
            capability.version,
            payload,
            now,
            now,
            now,
        ))

        append_event(
            connection,
            user_id,
            run_id,
            "workflow.created",
        )

        return dict(
            select_run(connection, user_id, run_id)
        )


def get_workflow(user_id, run_id, path):
    with connect(path) as connection:
        connection.execute("BEGIN")

        run = dict(
            select_run(connection, user_id, run_id)
        )

        rows = connection.execute("""
            SELECT id, step_key, capability,
                   capability_version, status,
                   attempt_count, error_code,
                   output_payload,
                   created_at, updated_at
            FROM workflow_steps
            WHERE user_id = ? AND run_id = ?
            ORDER BY created_at, id
        """, (
            user_id,
            run["id"],
        )).fetchall()

        steps = []

        for row in rows:
            step = dict(row)

            output = step.pop("output_payload")

            step["output"] = (
                json.loads(output)
                if output is not None else None
            )

            steps.append(step)

        run["steps"] = steps

        return run


def list_workflows(user_id, path, limit=50, offset=0):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid page size")

    if type(offset) is not int or not 0 <= offset <= 1000:
        raise ValueError("Invalid offset")

    with connect(path) as connection:
        rows = connection.execute("""
            SELECT *
            FROM workflow_runs
            WHERE user_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT ? OFFSET ?
        """, (
            user_id,
            limit + 1,
            offset,
        )).fetchall()

    return {
        "records": [dict(row) for row in rows[:limit]],
        "next_offset": (
            offset + limit
            if len(rows) > limit else None
        ),
    }


def list_events(
    user_id,
    run_id,
    path,
    after_id=0,
    limit=100,
):
    if (
        type(after_id) is not int
        or not 0 <= after_id <= 9007199254740991
    ):
        raise ValueError("Invalid event cursor")

    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid page size")

    with connect(path) as connection:
        connection.execute("BEGIN")

        run = select_run(
            connection,
            user_id,
            run_id,
        )

        rows = connection.execute("""
            SELECT id, run_id, step_id,
                   event_type, created_at
            FROM workflow_events
            WHERE user_id = ?
                AND run_id = ?
                AND id > ?
            ORDER BY id
            LIMIT ?
        """, (
            user_id,
            run["id"],
            after_id,
            limit + 1,
        )).fetchall()

    events = [dict(row) for row in rows[:limit]]

    return {
        "events": events,
        "next_cursor": (
            events[-1]["id"]
            if events else after_id
        ),
        "has_more": len(rows) > limit,
    }


def cancel_workflow(
    user_id,
    run_id,
    expected_revision,
    path,
):
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        run = select_run(
            connection,
            user_id,
            run_id,
        )

        if run["revision"] != expected_revision:
            raise WorkflowConflict()

        if run["status"] in TERMINAL_STATES:
            return dict(run)

        if run["status"] not in {
            "queued", "running",
        }:
            raise WorkflowConflict()

        if run["cancellation_requested"]:
            return dict(run)

        now = int(time.time())
        identifier = run["id"]

        status = (
            "cancelled"
            if run["status"] == "queued"
            else "running"
        )

        connection.execute("""
            UPDATE workflow_runs
            SET cancellation_requested = 1,
                status = ?,
                revision = revision + 1,
                updated_at = ?
            WHERE user_id = ? AND id = ?
        """, (
            status,
            now,
            user_id,
            identifier,
        ))

        connection.execute("""
            UPDATE workflow_steps
            SET status = 'cancelled',
                revision = revision + 1,
                updated_at = ?
            WHERE user_id = ?
                AND run_id = ?
                AND status = 'queued'
        """, (
            now,
            user_id,
            identifier,
        ))

        append_event(
            connection,
            user_id,
            identifier,
            (
                "workflow.cancelled"
                if status == "cancelled"
                else "workflow.cancellation_requested"
            ),
        )

        return dict(
            select_run(
                connection,
                user_id,
                identifier,
            )
        )


class WorkflowLeaseLost(Exception):
    pass


LEASE_SECONDS = 120


def recover_expired(connection, user_id, run_id, now):
    """Recover an interrupted single-step local workflow."""

    run = select_run(connection, user_id, run_id)

    if run["status"] != "running":
        return

    step = connection.execute("""
        SELECT *
        FROM workflow_steps
        WHERE user_id = ?
            AND run_id = ?
            AND status = 'running'
            AND lease_expires_at <= ?
    """, (user_id, run_id, now)).fetchone()

    if step is None:
        return

    try:
        capability = resolve_capability(step["capability"])
        retry_safe = (
            capability.retry_safe
            and capability.version == step["capability_version"]
        )
    except ValueError:
        retry_safe = False

    if not retry_safe:
        status = "uncertain"
        error = "interrupted_operation"
    elif run["cancellation_requested"]:
        status = "cancelled"
        error = None
    elif step["attempt_count"] >= 3:
        status = "failed"
        error = "attempt_limit"
    else:
        status = "queued"
        error = None

    connection.execute("""
        UPDATE workflow_steps
        SET status = ?,
            error_code = ?,
            lease_token = NULL,
            lease_expires_at = NULL,
            available_at = ?,
            updated_at = ?,
            revision = revision + 1
        WHERE user_id = ? AND id = ?
    """, (
        status, error, now, now,
        user_id, step["id"],
    ))

    connection.execute("""
        UPDATE workflow_runs
        SET status = ?,
            updated_at = ?,
            revision = revision + 1
        WHERE user_id = ? AND id = ?
    """, (status, now, user_id, run_id))

    append_event(
        connection, user_id, run_id,
        "workflow.recovered"
        if status == "queued"
        else "workflow." + status,
        step["id"],
    )


def claim_workflow(user_id, run_id, path):
    """Atomically lease one queued operation."""

    run_id = canonical_id(run_id)

    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        now = int(time.time())

        recover_expired(
            connection, user_id, run_id, now,
        )

        run = select_run(connection, user_id, run_id)

        if (
            run["status"] != "queued"
            or run["cancellation_requested"]
        ):
            return None

        step = connection.execute("""
            SELECT *
            FROM workflow_steps
            WHERE user_id = ?
                AND run_id = ?
                AND status = 'queued'
                AND available_at <= ?
                AND attempt_count < 3
            ORDER BY created_at, id
            LIMIT 1
        """, (
            user_id, run_id, now,
        )).fetchone()

        if step is None:
            return None

        token = str(uuid4())

        connection.execute("""
            UPDATE workflow_steps
            SET status = 'running',
                attempt_count = attempt_count + 1,
                lease_token = ?,
                lease_expires_at = ?,
                updated_at = ?,
                revision = revision + 1
            WHERE user_id = ? AND id = ?
        """, (
            token, now + LEASE_SECONDS, now,
            user_id, step["id"],
        ))

        connection.execute("""
            UPDATE workflow_runs
            SET status = 'running',
                updated_at = ?,
                revision = revision + 1
            WHERE user_id = ? AND id = ?
        """, (now, user_id, run_id))

        append_event(
            connection, user_id, run_id,
            "workflow.started", step["id"],
        )

        result = dict(step)
        result["lease_token"] = token
        result["lease_expires_at"] = now + LEASE_SECONDS
        result["attempt_count"] += 1
        result["status"] = "running"

        return result


def finish_workflow(
    user_id,
    run_id,
    step_id,
    lease_token,
    path,
    *,
    output=None,
    error_code=None,
):
    """Commit only the result of the current lease holder."""

    run_id = canonical_id(run_id)
    step_id = canonical_id(step_id)

    allowed_errors = {
        "permission_denied",
        "target_unavailable",
        "operation_failed",
        "result_limit",
        "invalid_contract",
    }

    if error_code is not None:
        if error_code not in allowed_errors:
            raise ValueError("Invalid workflow error")
        if output is not None:
            raise ValueError("Failed operation cannot have output")

    elif output is None:
        raise ValueError("Completed operation requires output")

    payload = (
        encode_payload(output)
        if output is not None else None
    )

    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        now = int(time.time())

        run = select_run(connection, user_id, run_id)

        step = connection.execute("""
            SELECT *
            FROM workflow_steps
            WHERE user_id = ?
                AND run_id = ?
                AND id = ?
        """, (
            user_id, run_id, step_id,
        )).fetchone()

        if (
            step is None
            or run["status"] != "running"
            or step["status"] != "running"
            or step["lease_token"] != lease_token
            or step["lease_expires_at"] is None
            or step["lease_expires_at"] <= now
        ):
            raise WorkflowLeaseLost()

        if run["cancellation_requested"]:
            status = "cancelled"
            payload = None
            error_code = None

        elif error_code is not None:
            status = "failed"

        else:
            status = "completed"

        connection.execute("""
            UPDATE workflow_steps
            SET status = ?,
                output_payload = ?,
                error_code = ?,
                lease_token = NULL,
                lease_expires_at = NULL,
                updated_at = ?,
                revision = revision + 1
            WHERE user_id = ? AND id = ?
        """, (
            status, payload, error_code,
            now, user_id, step_id,
        ))

        connection.execute("""
            UPDATE workflow_runs
            SET status = ?,
                updated_at = ?,
                revision = revision + 1
            WHERE user_id = ? AND id = ?
        """, (status, now, user_id, run_id))

        append_event(
            connection, user_id, run_id,
            "workflow." + status, step_id,
        )

        return dict(
            select_run(connection, user_id, run_id)
        )
