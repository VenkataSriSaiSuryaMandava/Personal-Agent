import time
from pathlib import Path

from aegis.storage.database import (
    DATABASE_PATH,
    connect,
)


from aegis.storage.settings import ApplicationSettings


SCHEMA_VERSION = 8


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

            version = 7

        if version == 7:

            connection.execute("""
                CREATE TABLE job_sources (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    provider TEXT NOT NULL CHECK (
                        provider IN (
                            'greenhouse', 'lever', 'ashby'
                        )
                    ),
                    board TEXT NOT NULL CHECK (
                        length(board) BETWEEN 1 AND 100
                    ),
                    company TEXT NOT NULL CHECK (
                        length(company) BETWEEN 1 AND 160
                    ),
                    enabled INTEGER NOT NULL DEFAULT 1
                        CHECK (enabled IN (0, 1)),
                    revision INTEGER NOT NULL DEFAULT 1
                        CHECK (
                            revision BETWEEN 1
                            AND 9007199254740991
                        ),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    last_attempt_at INTEGER,
                    last_success_at INTEGER,
                    last_result TEXT NOT NULL DEFAULT 'never'
                        CHECK (
                            last_result IN (
                                'never', 'success',
                                'failed', 'limited'
                            )
                        ),
                    FOREIGN KEY (user_id)
                        REFERENCES users(id)
                        ON DELETE CASCADE,
                    UNIQUE(user_id, provider, board),
                    UNIQUE(user_id, id)
                )
            """)

            connection.execute("""
                CREATE INDEX idx_job_sources_owner
                ON job_sources(user_id, enabled)
            """)

            connection.execute("""
                CREATE TABLE job_listings (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    source_id TEXT NOT NULL,
                    external_id TEXT NOT NULL CHECK (
                        length(external_id) BETWEEN 1 AND 200
                    ),
                    title TEXT NOT NULL CHECK (
                        length(title) BETWEEN 1 AND 160
                    ),
                    location TEXT NOT NULL DEFAULT ''
                        CHECK (length(location) <= 500),
                    department TEXT NOT NULL DEFAULT ''
                        CHECK (length(department) <= 300),
                    description TEXT NOT NULL DEFAULT ''
                        CHECK (length(description) <= 30000),
                    employment_type TEXT NOT NULL DEFAULT ''
                        CHECK (length(employment_type) <= 100),
                    work_mode TEXT NOT NULL DEFAULT 'unknown'
                        CHECK (
                            work_mode IN (
                                'unknown', 'remote',
                                'hybrid', 'onsite'
                            )
                        ),
                    posting_url TEXT NOT NULL CHECK (
                        length(posting_url) BETWEEN 1 AND 2000
                    ),
                    apply_url TEXT NOT NULL DEFAULT ''
                        CHECK (length(apply_url) <= 2000),
                    published_at INTEGER,
                    first_seen_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL,
                    is_open INTEGER NOT NULL DEFAULT 1
                        CHECK (is_open IN (0, 1)),
                    FOREIGN KEY (user_id, source_id)
                        REFERENCES job_sources(user_id, id)
                        ON DELETE CASCADE,
                    UNIQUE(user_id, source_id, external_id)
                )
            """)

            connection.execute("""
                CREATE INDEX idx_job_listings_owner_seen
                ON job_listings(
                    user_id, is_open, last_seen_at DESC
                )
            """)

            connection.execute("""
                CREATE TABLE job_application_links (
                    user_id INTEGER NOT NULL,
                    application_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL CHECK (
                        provider IN (
                            'greenhouse', 'lever', 'ashby'
                        )
                    ),
                    board TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY (user_id)
                        REFERENCES users(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (application_id)
                        REFERENCES workspace_records(id)
                        ON DELETE CASCADE,
                    UNIQUE(
                        user_id, provider,
                        board, external_id
                    )
                )
            """)

            connection.execute("""
                CREATE TRIGGER job_application_owner_check
                BEFORE INSERT ON job_application_links
                BEGIN
                    SELECT RAISE(
                        ABORT, 'Invalid job application'
                    )
                    WHERE NOT EXISTS (
                        SELECT 1 FROM workspace_records
                        WHERE id = NEW.application_id
                        AND user_id = NEW.user_id
                        AND workspace = 'jobs'
                    );
                END
            """)

            connection.execute("""
                CREATE TRIGGER job_application_update_check
                BEFORE UPDATE ON job_application_links
                BEGIN
                    SELECT RAISE(
                        ABORT, 'Invalid job application'
                    )
                    WHERE NOT EXISTS (
                        SELECT 1 FROM workspace_records
                        WHERE id = NEW.application_id
                        AND user_id = NEW.user_id
                        AND workspace = 'jobs'
                    );
                END
            """)

            connection.execute("PRAGMA user_version = 8")
