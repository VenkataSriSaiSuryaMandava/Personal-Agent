from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aegis.storage.settings import ApplicationSettings


class SettingsPatchRequest(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    expected_revision: int = Field(
        ge=1,
        le=9_223_372_036_854_775_807,
    )

    changes: dict[str, Any] = Field(
        min_length=1,
        max_length=9,
    )


class SettingsResetRequest(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    expected_revision: int = Field(
        ge=1,
        le=9_223_372_036_854_775_807,
    )


class SettingsResponse(BaseModel):

    settings: ApplicationSettings
    revision: int
    updated_at: int

    editable_fields: list[str]

    security_enforcement_active: bool = False


class ProviderStatus(BaseModel):

    provider: Literal["gemini", "groq"]

    configured: bool
    implemented: bool

    model: str | None = None

    status: Literal[
        "configured",
        "not_configured",
        "not_implemented",
        "invalid_configuration",
    ]

    live_verified: bool = False


class ProvidersResponse(BaseModel):

    providers: list[ProviderStatus]

    primary_provider: str
    fallback_provider: str
    fallback_enabled: bool

    fallback_implemented: bool = False


class AuditEvent(BaseModel):

    id: int
    event_type: Literal[
        "settings.updated",
        "emergency_stop.enabled",
        "emergency_stop.disabled",
    ]
    settings_revision: int
    created_at: int


class AuditResponse(BaseModel):

    events: list[AuditEvent]

    next_before_id: int | None = None


class StorageResponse(BaseModel):

    database: Literal["sqlite"] = "sqlite"
    schema_version: int
    expected_schema_version: int

    integrity: Literal["ok", "failed"]

    local_only: bool = True
    encrypted_by_application: bool = False
