"""Strict schemas for private career information."""

import unicodedata
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

ShortText = Annotated[str, Field(max_length=300)]

MAX_REVISION = 9007199254740991
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_RESUME_VERSIONS = 20
MAX_EXTRACTED_TEXT = 100000

MediaType = Literal[
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
]


def clean_text(value: str) -> str:
    value.encode("utf-8", errors="strict")

    if any(
        unicodedata.category(char) in {"Cc", "Cf"}
        and char not in "\n\r\t"
        for char in value
    ):
        raise ValueError("Invalid text")

    return value.strip()


class CareerProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    full_name: ShortText = ""
    email: ShortText = ""
    phone: ShortText = ""
    location: ShortText = ""
    headline: ShortText = ""

    summary: str = Field(default="", max_length=8000)

    skills: list[ShortText] = Field(
        default_factory=list, max_length=100
    )

    education: str = Field(default="", max_length=12000)
    experience: str = Field(default="", max_length=20000)
    projects: str = Field(default="", max_length=12000)

    target_roles: list[ShortText] = Field(
        default_factory=list, max_length=30
    )

    target_locations: list[ShortText] = Field(
        default_factory=list, max_length=30
    )

    work_mode: Literal[
        "any", "remote", "hybrid", "onsite"
    ] = "any"

    employment_type: Literal[
        "any", "full_time", "part_time",
        "contract", "internship"
    ] = "any"

    work_authorization: str = Field(
        default="", max_length=1000
    )

    sponsorship_required: Literal[
        "unknown", "yes", "no"
    ] = "unknown"

    salary_currency: str = Field(
        default="USD", pattern=r"^[A-Z]{3}$"
    )

    salary_min: int | None = Field(
        default=None, ge=0, le=10000000
    )

    salary_max: int | None = Field(
        default=None, ge=0, le=10000000
    )

    linkedin_url: str = Field(default="", max_length=2000)
    portfolio_url: str = Field(default="", max_length=2000)
    github_url: str = Field(default="", max_length=2000)

    @field_validator("*")
    @classmethod
    def validate_text(cls, value):
        if isinstance(value, str):
            return clean_text(value)

        if isinstance(value, list):
            cleaned = [clean_text(item) for item in value]
            return list(dict.fromkeys(
                item for item in cleaned if item
            ))

        return value

    @model_validator(mode="after")
    def validate_salary(self):
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            raise ValueError("Invalid salary range")

        return self


class CareerProfileUpdate(CareerProfile):
    expected_revision: int = Field(
        ge=0, le=MAX_REVISION
    )


class ResumeMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(min_length=1, max_length=160)
    media_type: MediaType

    @field_validator("title")
    @classmethod
    def validate_title(cls, value):
        value = clean_text(value)

        if not value or any(
            char in value for char in "\n\r\t"
        ):
            raise ValueError("Invalid resume title")

        return value


class ResumeTextUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    extracted_text: str = Field(
        max_length=MAX_EXTRACTED_TEXT
    )

    @field_validator("extracted_text")
    @classmethod
    def validate_content(cls, value):
        return clean_text(value)
