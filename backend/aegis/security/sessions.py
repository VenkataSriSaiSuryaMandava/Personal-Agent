import hashlib
import secrets
import re
import time

from pathlib import Path
from typing import Callable

from aegis.storage.database import (
    DATABASE_PATH,
    connect,
)


SESSION_DURATION = 12 * 60 * 60
IDLE_TIMEOUT = 30 * 60


class SessionDenied(Exception):
    """Session is invalid or unauthorized."""


def hash_token(token: str) -> str:

    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def valid_token_format(token: str) -> bool:

    return (
        isinstance(token, str)
        and re.fullmatch(
            r"[A-Za-z0-9_-]{43}",
            token,
        ) is not None
    )


class SessionManager:

    def __init__(
        self,
        path: Path = DATABASE_PATH,
        clock: Callable[[], float] = time.time,
    ):

        self.path = path
        self.clock = clock

    def create_session(self, user_id: int) -> str:

        token = secrets.token_urlsafe(32)
        token_hash = hash_token(token)

        with connect(self.path) as connection:

            connection.execute("BEGIN IMMEDIATE")

            now = int(self.clock())

            owner = connection.execute("""
                SELECT id
                FROM users
                WHERE id = ?
                AND is_active = 1
            """, (user_id,)).fetchone()

            if owner is None:

                raise SessionDenied(
                    "Session creation denied"
                )

            connection.execute("""
                INSERT INTO auth_sessions (
                    user_id,
                    token_hash,
                    created_at,
                    expires_at,
                    last_seen_at
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                user_id,
                token_hash,
                now,
                now + SESSION_DURATION,
                now,
            ))

        return token

    def validate_session(self, token: str) -> int:

        if not valid_token_format(token):

            raise SessionDenied(
                "Invalid session"
            )

        token_hash = hash_token(token)

        with connect(self.path) as connection:

            connection.execute("BEGIN IMMEDIATE")

            now = int(self.clock())

            session = connection.execute("""
                SELECT
                    s.id,
                    s.user_id,
                    s.created_at,
                    s.expires_at,
                    s.last_seen_at,
                    s.revoked_at,
                    u.is_active
                FROM auth_sessions AS s
                JOIN users AS u
                    ON s.user_id = u.id
                WHERE s.token_hash = ?
            """, (token_hash,)).fetchone()

            if (
                session is None
                or session["revoked_at"] is not None
                or session["is_active"] != 1
                or now < session["last_seen_at"]
                or now >= session["expires_at"]
                or now - session["last_seen_at"]
                    >= IDLE_TIMEOUT
            ):

                raise SessionDenied(
                    "Invalid or expired session"
                )

            connection.execute("""
                UPDATE auth_sessions
                SET last_seen_at = ?
                WHERE id = ?
            """, (now, session["id"]))

            return session["user_id"]

    def revoke_session(self, token: str) -> None:

        if not valid_token_format(token):
            return

        with connect(self.path) as connection:

            connection.execute("""
                UPDATE auth_sessions
                SET revoked_at = ?
                WHERE token_hash = ?
                AND revoked_at IS NULL
            """, (
                int(self.clock()),
                hash_token(token),
            ))

    def revoke_all_sessions(
        self,
        user_id: int,
    ) -> None:

        with connect(self.path) as connection:

            connection.execute("""
                UPDATE auth_sessions
                SET revoked_at = ?
                WHERE user_id = ?
                AND revoked_at IS NULL
            """, (
                int(self.clock()),
                user_id,
            ))


    def cleanup_expired_sessions(self) -> int:

        with connect(self.path) as connection:

            connection.execute("BEGIN IMMEDIATE")

            now = int(self.clock())

            cursor = connection.execute("""
                DELETE FROM auth_sessions
                WHERE expires_at <= ?
                OR last_seen_at <= ?
                OR revoked_at IS NOT NULL
            """, (
                now,
                now - IDLE_TIMEOUT,
            ))

            return cursor.rowcount
