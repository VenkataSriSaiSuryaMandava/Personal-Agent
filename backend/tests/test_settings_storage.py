import sqlite3

import pytest
from pydantic import ValidationError

from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database
from aegis.storage.settings import (
    ApplicationSettings,
    SettingsConflict,
    SettingsUnavailable,
    load_settings,
    save_settings,
)


@pytest.fixture
def settings_database(tmp_path):

    path = tmp_path / "private" / "settings.sqlite3"

    initialize_database(path)

    return path


def updated(settings, **changes):

    return ApplicationSettings.model_validate({
        **settings.model_dump(),
        **changes,
    })


def test_schema_version(settings_database):

    with connect(settings_database) as connection:

        assert connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 3


def test_default_settings(settings_database):

    snapshot = load_settings(settings_database)

    assert snapshot.revision == 1
    assert snapshot.settings.theme == "dark"
    assert snapshot.settings.primary_provider == "gemini"
    assert snapshot.settings.fallback_provider == "groq"
    assert snapshot.settings.cloud_enabled is False
    assert snapshot.settings.fallback_enabled is False
    assert snapshot.settings.retain_conversations is False
    assert snapshot.settings.emergency_stop is False


@pytest.mark.parametrize("invalid", [
    {"theme": "invalid"},
    {"primary_provider": "unknown"},
    {"fallback_provider": "gemini"},
    {"cloud_enabled": "true"},
    {"emergency_stop": 1},
    {"retain_conversations": None},
    {"unknown_field": True},
    {"response_style": "invalid"},
])
def test_invalid_settings_rejected(invalid):

    with pytest.raises(ValidationError):
        ApplicationSettings.model_validate(invalid)


def test_settings_persist(settings_database):

    initial = load_settings(settings_database)

    save_settings(
        updated(
            initial.settings,
            theme="light",
            response_style="detailed",
        ),
        initial.revision,
        settings_database,
    )

    result = load_settings(settings_database)

    assert result.settings.theme == "light"
    assert result.settings.response_style == "detailed"
    assert result.revision == 2


def test_reinitialization_preserves_settings(
    settings_database,
):

    initial = load_settings(settings_database)

    expected = save_settings(
        updated(initial.settings, theme="light"),
        initial.revision,
        settings_database,
    )

    initialize_database(settings_database)

    assert load_settings(settings_database) == expected


def test_stale_revision_rejected(settings_database):

    original = load_settings(settings_database)

    save_settings(
        updated(original.settings, theme="light"),
        original.revision,
        settings_database,
    )

    with pytest.raises(SettingsConflict):

        save_settings(
            updated(original.settings, theme="system"),
            original.revision,
            settings_database,
        )

    assert load_settings(
        settings_database
    ).settings.theme == "light"


@pytest.mark.parametrize("revision", [
    0,
    -1,
    True,
    "1",
])
def test_invalid_revision(settings_database, revision):

    with pytest.raises(ValueError):

        save_settings(
            ApplicationSettings(),
            revision,
            settings_database,
        )


def test_no_op_does_not_create_revision(
    settings_database,
):

    initial = load_settings(settings_database)

    result = save_settings(
        initial.settings,
        initial.revision,
        settings_database,
    )

    assert result == initial


def test_audit_event_created(settings_database):

    initial = load_settings(settings_database)

    save_settings(
        updated(initial.settings, theme="light"),
        initial.revision,
        settings_database,
    )

    with connect(settings_database) as connection:

        row = connection.execute("""
            SELECT event_type, settings_revision
            FROM security_audit_events
        """).fetchone()

        assert row["event_type"] == "settings.updated"
        assert row["settings_revision"] == 2


def test_emergency_stop_persistence(settings_database):

    initial = load_settings(settings_database)

    save_settings(
        updated(initial.settings, emergency_stop=True),
        initial.revision,
        settings_database,
    )

    assert load_settings(
        settings_database
    ).settings.emergency_stop is True


def test_emergency_stop_audit(settings_database):

    initial = load_settings(settings_database)

    enabled = save_settings(
        updated(initial.settings, emergency_stop=True),
        initial.revision,
        settings_database,
    )

    save_settings(
        updated(enabled.settings, emergency_stop=False),
        enabled.revision,
        settings_database,
    )

    with connect(settings_database) as connection:

        events = [
            row[0]
            for row in connection.execute("""
                SELECT event_type
                FROM security_audit_events
                ORDER BY id
            """)
        ]

    assert events == [
        "settings.updated",
        "emergency_stop.enabled",
        "settings.updated",
        "emergency_stop.disabled",
    ]


def test_audit_failure_rolls_back_settings(
    settings_database,
):

    original = load_settings(settings_database)

    with connect(settings_database) as connection:

        connection.execute("""
            CREATE TRIGGER reject_audit
            BEFORE INSERT ON security_audit_events
            BEGIN
                SELECT RAISE(ABORT, 'Synthetic test failure');
            END
        """)

    with pytest.raises(sqlite3.IntegrityError):

        save_settings(
            updated(original.settings, theme="light"),
            original.revision,
            settings_database,
        )

    assert load_settings(settings_database) == original


def test_missing_settings_fail_closed(settings_database):

    with connect(settings_database) as connection:
        connection.execute("DELETE FROM application_settings")

    with pytest.raises(SettingsUnavailable):
        load_settings(settings_database)


def test_corrupted_settings_rejected(settings_database):

    with connect(settings_database) as connection:

        connection.execute("""
            UPDATE application_settings
            SET payload = 'invalid-json'
            WHERE id = 1
        """)

    with pytest.raises(ValidationError):
        load_settings(settings_database)


def test_migration_from_version_two_preserves_owner(
    settings_database,
):

    with connect(settings_database) as connection:

        connection.execute("DROP TABLE security_audit_events")
        connection.execute("DROP TABLE application_settings")

        connection.execute("""
            INSERT INTO users (
                id, username, password_hash, created_at
            )
            VALUES (1, 'synthetic-owner', 'test-hash', 100)
        """)

        connection.execute("""
            INSERT INTO auth_sessions (
                user_id, token_hash, created_at,
                expires_at, last_seen_at
            )
            VALUES (1, 'test-session-hash', 100, 200, 100)
        """)

        connection.execute("""
            INSERT INTO api_usage (provider, created_at)
            VALUES ('gemini', 100)
        """)

        connection.execute("PRAGMA user_version = 2")

    initialize_database(settings_database)

    assert load_settings(settings_database).revision == 1

    with connect(settings_database) as connection:

        assert connection.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0] == 1

        assert connection.execute(
            "SELECT COUNT(*) FROM auth_sessions"
        ).fetchone()[0] == 1

        assert connection.execute(
            "SELECT COUNT(*) FROM api_usage"
        ).fetchone()[0] == 1


def test_migration_failure_rolls_back(settings_database):

    with connect(settings_database) as connection:

        connection.execute("DROP TABLE application_settings")
        connection.execute("PRAGMA user_version = 2")

    with pytest.raises(sqlite3.OperationalError):
        initialize_database(settings_database)

    with connect(settings_database) as connection:

        assert connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 2

        assert connection.execute("""
            SELECT COUNT(*) FROM sqlite_master
            WHERE name = 'application_settings'
        """).fetchone()[0] == 0
