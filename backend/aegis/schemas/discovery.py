"""Validated configuration for public employer job boards."""

import re
import unicodedata

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

Provider = Literal["greenhouse", "lever", "ashby"]

MAX_SOURCES = 100
MAX_LISTINGS_PER_SOURCE = 1000
MAX_CACHE_BYTES = 64 * 1024 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

CACHE_TTL = 6 * 60 * 60
CACHE_RETENTION = 7 * 24 * 60 * 60

REQUEST_TIMEOUT = 15
MAX_CONCURRENT_REQUESTS = 3
MAX_REVISION = 9007199254740991

BOARD_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}",
    flags=re.ASCII,
)


class JobSourceInput(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
    )

    provider: Provider
    board: str = Field(min_length=1, max_length=100)
    company: str = Field(min_length=1, max_length=160)
    enabled: bool = True

    @field_validator("board")
    @classmethod
    def validate_board(cls, value):
        if not BOARD_PATTERN.fullmatch(value):
            raise ValueError("Invalid board identifier")

        return value

    @field_validator("company")
    @classmethod
    def validate_company(cls, value):
        value.encode("utf-8", errors="strict")

        if any(
            unicodedata.category(char) in {"Cc", "Cf"}
            for char in value
        ):
            raise ValueError("Invalid company name")

        value = value.strip()

        if not value:
            raise ValueError("Company name is required")

        return value


class JobListing(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
    )

    external_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=160)
    location: str = Field(default="", max_length=500)
    department: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=30000)
    employment_type: str = Field(default="", max_length=100)

    work_mode: Literal[
        "unknown", "remote", "hybrid", "onsite"
    ] = "unknown"

    posting_url: str = Field(min_length=1, max_length=2000)
    apply_url: str = Field(default="", max_length=2000)

    published_at: int | None = Field(
        default=None,
        ge=0,
        le=253402300799,
    )


class SourceAction(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
    )

    id: str = Field(min_length=36, max_length=36)
    action: Literal["update", "delete", "refresh"]

    expected_revision: int = Field(
        ge=1,
        le=MAX_REVISION,
    )

    source: JobSourceInput | None = None
    force: bool = False


class SaveJobInput(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
    )

    id: str = Field(min_length=36, max_length=36)
