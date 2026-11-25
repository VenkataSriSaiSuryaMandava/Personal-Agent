from pathlib import Path

from aegis.security.request_storage import public_runtime
from aegis.security.runtime_policy import ai_enabled

from aegis.schemas.settings import (
    AuditEvent,
    AuditResponse,
    ProvidersResponse,
    ProviderStatus,
    SettingsResponse,
    StorageResponse,
)

from aegis.models.registry import (
    PROVIDERS,
    provider_diagnostics,
)

from aegis.storage.database import DATABASE_PATH, connect
from aegis.storage.migrations import SCHEMA_VERSION

from aegis.storage.settings import (
    ApplicationSettings,
    SettingsConflict,
    SettingsSnapshot,
    SettingsUnavailable,
    load_settings,
    save_settings,
)


GENERAL_FIELDS = frozenset({
    "theme",
    "startup_workspace",
    "response_style",
})

SECURITY_FIELDS = frozenset({
    "cloud_enabled",
    "emergency_stop",
    "retain_conversations",
})

EDITABLE_FIELDS = GENERAL_FIELDS | SECURITY_FIELDS


def editable_fields():
    if public_runtime() or not ai_enabled():
        return EDITABLE_FIELDS - {
            "cloud_enabled",
            "retain_conversations",
        }

    return EDITABLE_FIELDS


class UnsupportedSetting(ValueError):
    """Requested setting is not currently editable."""


def serialize_settings(
    snapshot: SettingsSnapshot,
) -> SettingsResponse:

    preferences = snapshot.settings

    if public_runtime() or not ai_enabled():
        preferences = preferences.model_copy(
            update={
                "cloud_enabled": False,
                "retain_conversations": False,
                "fallback_enabled": False,
            },
        )

    return SettingsResponse(
        settings=preferences,
        revision=snapshot.revision,
        updated_at=snapshot.updated_at,
        editable_fields=sorted(editable_fields()),
        security_enforcement_active=True,
    )


class SettingsService:

    def __init__(
        self,
        path: Path = DATABASE_PATH,
    ):
        self.path = path

    def get(self) -> SettingsResponse:

        return serialize_settings(
            load_settings(self.path)
        )

    def update(
        self,
        changes: dict,
        expected_revision: int,
    ) -> SettingsResponse:

        if not changes:
            raise UnsupportedSetting(
                "No settings supplied"
            )

        if not set(changes).issubset(editable_fields()):
            raise UnsupportedSetting(
                "Setting is not currently editable"
            )

        current = load_settings(self.path)

        if current.revision != expected_revision:
            raise SettingsConflict(
                "Settings revision conflict"
            )

        updated = ApplicationSettings.model_validate({
            **current.settings.model_dump(),
            **changes,
        })

        result = save_settings(
            updated,
            expected_revision,
            self.path,
        )

        return serialize_settings(result)

    def reset(
        self,
        expected_revision: int,
    ) -> SettingsResponse:

        defaults = ApplicationSettings().model_dump()

        changes = {
            field: defaults[field]
            for field in GENERAL_FIELDS
        }

        # A general reset must never disable an emergency
        # stop or change existing provider permissions.
        return self.update(
            changes,
            expected_revision,
        )

    def providers(self) -> ProvidersResponse:

        snapshot = load_settings(self.path)
        preferences = snapshot.settings

        return ProvidersResponse(
            providers=[
                (
                    ProviderStatus(
                        provider=identifier,
                        configured=False,
                        implemented=identifier == "gemini",
                        model=None,
                        status="not_configured",
                        live_verified=False,
                    )
                    if not ai_enabled()
                    else ProviderStatus(
                        **provider_diagnostics(identifier)
                    )
                )
                for identifier in PROVIDERS
            ],
            primary_provider=preferences.primary_provider,
            fallback_provider=preferences.fallback_provider,
            fallback_enabled=False,
            fallback_implemented=False,
        )

    def audit(
        self,
        limit: int = 25,
        before_id: int | None = None,
    ) -> AuditResponse:

        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid audit limit")

        if before_id is not None and (
            type(before_id) is not int or before_id < 1
        ):
            raise ValueError("Invalid audit cursor")

        with connect(self.path) as connection:

            if before_id is None:

                rows = connection.execute("""
                    SELECT id, event_type,
                           settings_revision, created_at
                    FROM security_audit_events
                    ORDER BY id DESC
                    LIMIT ?
                """, (limit + 1,)).fetchall()

            else:

                rows = connection.execute("""
                    SELECT id, event_type,
                           settings_revision, created_at
                    FROM security_audit_events
                    WHERE id < ?
                    ORDER BY id DESC
                    LIMIT ?
                """, (
                    before_id,
                    limit + 1,
                )).fetchall()

        has_more = len(rows) > limit

        events = [
            AuditEvent.model_validate(dict(row))
            for row in rows[:limit]
        ]

        return AuditResponse(
            events=events,
            next_before_id=(
                events[-1].id
                if has_more and events
                else None
            ),
        )

    def storage(self) -> StorageResponse:

        if not self.path.is_file():
            raise SettingsUnavailable(
                "Database unavailable"
            )

        with connect(self.path) as connection:

            version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]

            if version != SCHEMA_VERSION:
                raise SettingsUnavailable(
                    "Database migration required"
                )

            checks = [
                row[0]
                for row in connection.execute(
                    "PRAGMA quick_check"
                )
            ]

        return StorageResponse(
            local_only=not public_runtime(),
            schema_version=version,
            expected_schema_version=SCHEMA_VERSION,
            integrity=(
                "ok" if checks == ["ok"] else "failed"
            ),
        )
