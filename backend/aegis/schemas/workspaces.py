from datetime import datetime, timezone
import unicodedata
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

Workspace = Literal[
    "tasks",
    "jobs",
    "email",
    "calendar",
    "research",
    "coding",
    "browser",
    "memory",
    "approvals",
]

STATUSES = {
    "tasks": (
        "todo", "in_progress", "completed",
    ),
    "jobs": (
        "saved", "applied", "interview",
        "offer", "rejected", "withdrawn",
    ),
    "email": (
        "draft", "archived",
    ),
    "calendar": (
        "planned", "completed", "cancelled",
    ),
    "research": (
        "planned", "in_progress", "completed",
    ),
    "coding": (
        "planned", "in_progress", "completed",
    ),
    "browser": (
        "saved", "reviewed", "archived",
    ),
    "memory": (
        "active", "archived",
    ),
    "approvals": (
        "pending", "approved", "rejected",
    ),
}


class WorkspaceRecord(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    title: str = Field(
        min_length=1,
        max_length=160,
    )

    status: str = Field(
        min_length=1,
        max_length=32,
    )

    notes: str = Field(
        default="",
        max_length=8000,
    )

    detail: str = Field(
        default="",
        max_length=500,
    )

    reference: str = Field(
        default="",
        max_length=2000,
    )

    scheduled_at: str = Field(
        default="",
        max_length=40,
    )

    priority: Literal[
        "low", "normal", "high"
    ] = "normal"


class WorkspaceUpdate(WorkspaceRecord):
    expected_revision: int = Field(
        ge=1,
        le=9007199254740991,
    )


def validate_record(
    workspace: str,
    record: WorkspaceRecord,
) -> WorkspaceRecord:

    if workspace not in STATUSES:
        raise ValueError("Invalid workspace")

    if record.status not in STATUSES[workspace]:
        raise ValueError("Invalid workspace status")

    if not record.title.strip():
        raise ValueError("Title is required")

    for text in (
        record.title,
        record.status,
        record.notes,
        record.detail,
        record.reference,
        record.scheduled_at,
    ):
        # Reject invalid Unicode, embedded nulls and
        # non-text control characters.
        text.encode("utf-8", errors="strict")

        if any(
            unicodedata.category(character) == "Cc"
            and character not in "\n\r\t"
            for character in text
        ):
            raise ValueError("Invalid text character")

    if any(
        character in record.title
        for character in ("\n", "\r", "\t")
    ):
        raise ValueError("Title must be single-line")

    if record.scheduled_at:
        value = datetime.fromisoformat(
            record.scheduled_at
        )

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "Timezone is required"
            )

        try:
            normalized_date = value.astimezone(
                timezone.utc
            )
        except (OverflowError, ValueError):
            raise ValueError(
                "Invalid event date"
            ) from None

        if not 1900 <= normalized_date.year <= 9999:
            raise ValueError("Invalid event year")

        record = record.model_copy(
            update={
                "scheduled_at":
                    normalized_date.isoformat()
            }
        )

    if (
        workspace == "calendar"
        and not record.scheduled_at
    ):
        raise ValueError("Event date is required")

    return record.model_copy(
        update={"title": record.title.strip()}
    )
