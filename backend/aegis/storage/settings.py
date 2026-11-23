import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from aegis.storage.database import DATABASE_PATH, connect


class ApplicationSettings(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
    )

    theme: Literal["dark", "light", "system"] = "dark"

    startup_workspace: Literal[
        "overview", "chat", "settings"
    ] = "overview"

    response_style: Literal[
        "balanced", "concise", "detailed"
    ] = "balanced"

    primary_provider: Literal[
        "gemini", "groq"
    ] = "gemini"

    fallback_provider: Literal[
        "gemini", "groq"
    ] = "groq"

    fallback_enabled: bool = False

    cloud_enabled: bool = False

    retain_conversations: bool = False

    emergency_stop: bool = False

    @model_validator(mode="after")
    def validate_providers(self):

        if self.primary_provider == self.fallback_provider:
            raise ValueError(
                "Primary and fallback providers must differ"
            )

        return self


@dataclass(frozen=True)
class SettingsSnapshot:

    settings: ApplicationSettings
    revision: int
    updated_at: int


class SettingsUnavailable(RuntimeError):
    """Settings are missing or unavailable."""


class SettingsConflict(RuntimeError):
    """Settings were modified by another operation."""


def _read_settings(connection) -> SettingsSnapshot:

    row = connection.execute("""
        SELECT payload, revision, updated_at
        FROM application_settings
        WHERE id = 1
    """).fetchone()

    if row is None:
        raise SettingsUnavailable(
            "Application settings are not initialized"
        )

    settings = ApplicationSettings.model_validate_json(
        row["payload"]
    )

    return SettingsSnapshot(
        settings=settings,
        revision=row["revision"],
        updated_at=row["updated_at"],
    )


def load_settings(
    path: Path = DATABASE_PATH,
) -> SettingsSnapshot:

    with connect(path) as connection:
        return _read_settings(connection)


def save_settings(
    settings: ApplicationSettings,
    expected_revision: int,
    path: Path = DATABASE_PATH,
) -> SettingsSnapshot:

    if type(expected_revision) is not int or expected_revision < 1:
        raise ValueError("Invalid settings revision")

    if not isinstance(settings, ApplicationSettings):
        raise TypeError("Invalid settings object")

    settings = ApplicationSettings.model_validate(
        settings.model_dump()
    )

    with connect(path) as connection:

        connection.execute("BEGIN IMMEDIATE")

        previous = _read_settings(connection)

        if previous.revision != expected_revision:
            raise SettingsConflict(
                "Settings have changed; reload before saving"
            )

        if previous.settings == settings:
            return previous

        now = max(
            int(time.time()),
            previous.updated_at,
        )

        revision = previous.revision + 1

        connection.execute("""
            UPDATE application_settings
            SET payload = ?,
                revision = ?,
                updated_at = ?
            WHERE id = 1
        """, (
            settings.model_dump_json(),
            revision,
            now,
        ))

        connection.execute("""
            INSERT INTO security_audit_events (
                event_type,
                settings_revision,
                created_at
            )
            VALUES (?, ?, ?)
        """, (
            "settings.updated",
            revision,
            now,
        ))

        if (
            previous.settings.emergency_stop
            != settings.emergency_stop
        ):
            event_type = (
                "emergency_stop.enabled"
                if settings.emergency_stop
                else "emergency_stop.disabled"
            )

            connection.execute("""
                INSERT INTO security_audit_events (
                    event_type,
                    settings_revision,
                    created_at
                )
                VALUES (?, ?, ?)
            """, (
                event_type,
                revision,
                now,
            ))

        return SettingsSnapshot(
            settings=settings,
            revision=revision,
            updated_at=now,
        )
