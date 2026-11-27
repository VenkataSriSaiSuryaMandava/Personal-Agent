"""Strict contracts for persistent agent workflows."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


WorkflowStatus = Literal[
    "queued",
    "running",
    "waiting_approval",
    "executing",
    "completed",
    "failed",
    "cancelled",
    "uncertain",
]

CapabilityName = Literal[
    "career.company_summary",
    "career.match_listing",
]

AgentName = Literal[
    "discovery",
    "matching",
    "research",
    "documents",
    "networking",
    "communication",
    "interview",
    "workflow",
]

MAX_WORKFLOW_STEPS = 20
MAX_WORKFLOW_PAYLOAD_BYTES = 32768
MAX_WORKFLOW_ATTEMPTS = 3
MAX_ACTIVE_WORKFLOWS = 20
MAX_GUEST_ACTIVE_WORKFLOWS = 2


class StrictContract(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
    )


class CompanySummaryInput(StrictContract):
    source_id: UUID


class MatchListingInput(StrictContract):
    listing_id: UUID


class WorkflowCreate(StrictContract):
    workflow_type: Literal[
        "company_summary",
        "match_listing",
    ]
    target_id: UUID = Field(strict=False)
    request_key: UUID = Field(strict=False)


class WorkflowCancel(StrictContract):
    expected_revision: int = Field(
        ge=1,
        le=9007199254740991,
    )


class DepartmentSummary(StrictContract):
    department: str = Field(max_length=300)
    count: int = Field(ge=0)


class CompanySummaryResult(StrictContract):
    source_id: str
    company: str = Field(max_length=160)
    provider: str
    board: str
    identity_verified: Literal[False]
    provenance: str
    open_listings: int = Field(ge=0)
    workplace_distribution: dict[str, int]
    top_departments: list[DepartmentSummary] = Field(
        max_length=10,
    )
    other_department_listings: int = Field(ge=0)
    last_success_at: int | None
    last_attempt_at: int | None
    last_result: str
    stale: bool
    unverified_fields: list[str] = Field(max_length=20)
    limitations: list[str] = Field(max_length=20)
