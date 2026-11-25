import time
from pathlib import Path

from aegis.storage.database import (
    DATABASE_PATH,
    connect,
)


from aegis.storage.settings import ApplicationSettings


SCHEMA_VERSION = 7


def initialize_database(
    path: Path = DATABASE_PATH,
) -> None:

    with connect(path) as connection:

        connection.execute("BEGIN IMMEDIATE")

        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        if version > SCHEMA_VERSION:
            raise RuntimeError(
                "Unsupported database schema version"
            )

        if version == 0:

            connection.execute("""
                CREATE TABLE IF NOT EXISTS app_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS api_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)

            connection.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_api_usage_created_at
                ON api_usage(created_at)
            """)

            connection.execute("""
                INSERT INTO app_metadata (key, value)
                VALUES ('application', 'Aegis AI')
                ON CONFLICT(key) DO NOTHING
            """)

            connection.execute(
                "PRAGMA user_version = 1"
            )


            version = 1

        if version == 1:

            connection.execute("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1
                        CHECK (is_active IN (0, 1))
                )
            """)

            connection.execute("""
                CREATE TABLE auth_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL,
                    revoked_at INTEGER,
                    FOREIGN KEY (user_id)
                        REFERENCES users(id)
                        ON DELETE CASCADE,
                    CHECK (expires_at > created_at)
                )
            """)

            connection.execute("""
                CREATE INDEX idx_auth_sessions_user
                ON auth_sessions(user_id)
            """)

            connection.execute("""
                CREATE INDEX idx_auth_sessions_expiry
                ON auth_sessions(expires_at)
            """)

            connection.execute("""
                CREATE TABLE login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    attempted_at INTEGER NOT NULL,
                    successful INTEGER NOT NULL
                        CHECK (successful IN (0, 1))
                )
            """)

            connection.execute("""
                CREATE INDEX idx_login_attempts_time
                ON login_attempts(attempted_at)
            """)

            connection.execute(
                "PRAGMA user_version = 2"
            )

            version = 2

        if version == 2:

            connection.execute("""
                CREATE TABLE application_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL,
                    revision INTEGER NOT NULL
                        CHECK (revision >= 1),
                    updated_at INTEGER NOT NULL
                        CHECK (updated_at >= 0)
                )
            """)

            connection.execute("""
                CREATE TABLE security_audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL CHECK (
                        event_type IN (
                            'settings.updated',
                            'emergency_stop.enabled',
                            'emergency_stop.disabled'
                        )
                    ),
                    settings_revision INTEGER NOT NULL
                        CHECK (settings_revision >= 1),
                    created_at INTEGER NOT NULL
                        CHECK (created_at >= 0)
                )
            """)

            connection.execute("""
                CREATE INDEX idx_security_audit_created_at
                ON security_audit_events(created_at)
            """)

            connection.execute("""
                INSERT INTO application_settings (
                    id,
                    payload,
                    revision,
                    updated_at
                )
                VALUES (1, ?, 1, ?)
            """, (
                ApplicationSettings().model_dump_json(),
                int(time.time()),
            ))

            connection.execute(
                "PRAGMA user_version = 3"
            )

            version = 3

        if version == 3:

            connection.execute("""
                CREATE TABLE conversations (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL
                        CHECK (length(title) BETWEEN 1 AND 120),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY (user_id)
                        REFERENCES users(id)
                        ON DELETE CASCADE
                )
            """)

            connection.execute("""
                CREATE INDEX idx_conversations_owner_updated
                ON conversations(user_id, updated_at DESC)
            """)

            connection.execute("""
                CREATE TABLE conversation_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    user_message TEXT NOT NULL
                        CHECK (length(user_message) BETWEEN 1 AND 4000),
                    assistant_message TEXT NOT NULL
                        CHECK (length(assistant_message) BETWEEN 1 AND 20000),
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY (conversation_id)
                        REFERENCES conversations(id)
                        ON DELETE CASCADE
                )
            """)

            connection.execute("""
                CREATE INDEX idx_conversation_turns_parent
                ON conversation_turns(conversation_id, id)
            """)

            connection.execute(
                "PRAGMA user_version = 4"
            )


            version = 4

        if version == 4:

            connection.execute("""
                CREATE TABLE workspace_records (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    workspace TEXT NOT NULL CHECK (
                        workspace IN (
                            'tasks', 'jobs', 'email',
                            'calendar', 'research', 'coding',
                            'browser', 'memory', 'approvals'
                        )
                    ),
                    payload TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1
                        CHECK (revision >= 1),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY (user_id)
                        REFERENCES users(id)
                        ON DELETE CASCADE
                )
            """)

            connection.execute("""
                CREATE INDEX idx_workspace_records_owner
                ON workspace_records(
                    user_id, workspace, updated_at DESC
                )
            """)

            connection.execute("PRAGMA user_version = 5")


            version = 5

        if version == 5:

            connection.execute("""
                CREATE TABLE workspace_audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    workspace TEXT NOT NULL CHECK (
                        workspace IN (
                            'tasks', 'jobs', 'email',
                            'calendar', 'research', 'coding',
                            'browser', 'memory', 'approvals'
                        )
                    ),
                    record_id TEXT NOT NULL,
                    event_type TEXT NOT NULL CHECK (
                        event_type IN (
                            'created', 'updated', 'deleted'
                        )
                    ),
                    revision INTEGER NOT NULL
                        CHECK (revision >= 1),
                    created_at INTEGER NOT NULL
                        CHECK (created_at >= 0),
                    FOREIGN KEY (user_id)
                        REFERENCES users(id)
                        ON DELETE CASCADE
                )
            """)

            connection.execute("""
                CREATE INDEX idx_workspace_audit_owner
                ON workspace_audit_events(user_id, id DESC)
            """)

            connection.execute("""
                CREATE TRIGGER workspace_audit_insert
                AFTER INSERT ON workspace_records
                BEGIN
                    INSERT INTO workspace_audit_events (
                        user_id, workspace, record_id,
                        event_type, revision, created_at
                    )
                    VALUES (
                        NEW.user_id, NEW.workspace, NEW.id,
                        'created', NEW.revision,
                        CAST(strftime('%s', 'now') AS INTEGER)
                    );
                END
            """)

            connection.execute("""
                CREATE TRIGGER workspace_audit_update
                AFTER UPDATE ON workspace_records
                BEGIN
                    INSERT INTO workspace_audit_events (
                        user_id, workspace, record_id,
                        event_type, revision, created_at
                    )
                    VALUES (
                        NEW.user_id, NEW.workspace, NEW.id,
                        'updated', NEW.revision,
                        CAST(strftime('%s', 'now') AS INTEGER)
                    );
                END
            """)

            connection.execute("""
                CREATE TRIGGER workspace_audit_delete
                AFTER DELETE ON workspace_records
                BEGIN
                    INSERT INTO workspace_audit_events (
                        user_id, workspace, record_id,
                        event_type, revision, created_at
                    )
                    SELECT
                        OLD.user_id, OLD.workspace, OLD.id,
                        'deleted', OLD.revision,
                        CAST(strftime('%s', 'now') AS INTEGER)
                    WHERE EXISTS (
                        SELECT 1 FROM users
                        WHERE id = OLD.user_id
                    );
                END
            """)

            connection.execute("PRAGMA user_version = 6")

            version = 6

        if version == 6:

            connection.execute("""
                CREATE TABLE career_profiles (
                    user_id INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1
                        CHECK (
                            revision BETWEEN 1
                            AND 9007199254740991
                        ),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY (user_id)
                        REFERENCES users(id)
                        ON DELETE CASCADE
                )
            """)

            connection.execute("""
                CREATE TABLE resume_versions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL
                        CHECK (length(title) BETWEEN 1 AND 160),
                    media_type TEXT NOT NULL CHECK (
                        media_type IN (
                            'application/pdf',
                            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                            'text/plain'
                        )
                    ),
                    document BLOB NOT NULL,
                    size_bytes INTEGER NOT NULL CHECK (
                        size_bytes BETWEEN 1 AND 10485760
                        AND size_bytes = length(document)
                    ),
                    sha256 TEXT NOT NULL
                        CHECK (length(sha256) = 64),
                    extracted_text TEXT NOT NULL
                        CHECK (length(extracted_text) <= 100000),
                    is_active INTEGER NOT NULL DEFAULT 0
                        CHECK (is_active IN (0, 1)),
                    revision INTEGER NOT NULL DEFAULT 1
                        CHECK (
                            revision BETWEEN 1
                            AND 9007199254740991
                        ),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY (user_id)
                        REFERENCES users(id)
                        ON DELETE CASCADE
                )
            """)

            connection.execute("""
                CREATE INDEX idx_resume_owner_created
                ON resume_versions(user_id, created_at DESC)
            """)

            connection.execute("""
                CREATE UNIQUE INDEX idx_resume_active
                ON resume_versions(user_id)
                WHERE is_active = 1
            """)

            connection.execute("""
                CREATE TABLE career_audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    entity_type TEXT NOT NULL CHECK (
                        entity_type IN ('profile', 'resume')
                    ),
                    entity_id TEXT NOT NULL,
                    event_type TEXT NOT NULL CHECK (
                        event_type IN (
                            'created', 'updated',
                            'deleted', 'activated'
                        )
                    ),
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY (user_id)
                        REFERENCES users(id)
                        ON DELETE CASCADE
                )
            """)

            connection.execute("""
                CREATE INDEX idx_career_audit_owner
                ON career_audit_events(user_id, id DESC)
            """)

            connection.execute("PRAGMA user_version = 7")
