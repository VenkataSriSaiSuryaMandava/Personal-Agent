"""Explainable local career matching contracts."""

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


MatchStatus = Literal[
    "matched",
    "mismatch",
    "unknown",
    "not_applicable",
]

DimensionName = Literal[
    "required_skills",
    "preferred_skills",
    "target_role",
    "location",
    "work_mode",
    "employment_type",
]


class MatchDimension(BaseModel):
    model_config = ConfigDict(
        strict=True, extra="forbid", frozen=True,
    )

    name: DimensionName
    weight: int = Field(ge=1, le=100)
    status: MatchStatus
    value: int | None = Field(default=None, ge=0, le=100)
    explanation: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def check_evidence(self):
        if self.status in {"unknown", "not_applicable"}:
            if self.value is not None:
                raise ValueError("Unknown evidence cannot be scored")

        elif self.value is None:
            raise ValueError("Known evidence requires a score")

        elif self.status == "mismatch" and self.value != 0:
            raise ValueError("Mismatch must have zero score")

        return self


class QualificationEvidence(BaseModel):
    model_config = ConfigDict(
        strict=True, extra="forbid",
    )

    skill: str = Field(min_length=1, max_length=300)

    importance: Literal[
        "required", "preferred", "unspecified",
    ]

    status: Literal[
        "profile_match", "resume_mention", "not_evidenced",
    ]

    listing_evidence: str = Field(
        min_length=1, max_length=500,
    )


class MatchResult(BaseModel):
    model_config = ConfigDict(
        strict=True, extra="forbid",
    )

    algorithm_version: Literal["1.0"] = "1.0"

    score: int | None = Field(
        default=None, ge=0, le=100,
    )

    evidence_coverage: int = Field(ge=0, le=100)
    evaluated_weight: int = Field(ge=0, le=100)
    applicable_weight: int = Field(ge=0, le=100)

    dimensions: list[MatchDimension] = Field(
        min_length=6, max_length=6,
    )

    qualifications: list[QualificationEvidence] = Field(
        default_factory=list, max_length=200,
    )

    review_items: list[str] = Field(
        default_factory=list, max_length=20,
    )

    limitations: list[str] = Field(
        max_length=20,
    )
