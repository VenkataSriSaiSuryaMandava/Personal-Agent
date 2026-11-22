import secrets
import sqlite3
import time

from pathlib import Path
from typing import Callable

from aegis.security.owner import (
    normalize_username,
    InvalidUsername,
)

from aegis.security.passwords import (
    hash_password,
    verify_password,
    MAX_PASSWORD_LENGTH,
)

from aegis.security.login_limit import (
    LoginRateLimiter,
    LOGIN_WINDOW,
    LoginStorageUnavailable,
)

from aegis.security.sessions import (
    SessionManager,
    SESSION_DURATION,
    IDLE_TIMEOUT,
    hash_token,
    SessionDenied,
)

from aegis.storage.database import (
    DATABASE_PATH,
    connect,
)


class AuthenticationDenied(Exception):
    """Authentication credentials are invalid."""


class AuthenticationUnavailable(Exception):
    """Secure authentication is unavailable."""


_dummy_hash = hash_password(
    secrets.token_urlsafe(32)
)


class AuthenticationService:

    def __init__(
        self,
        path: Path = DATABASE_PATH,
        clock: Callable[[], float] = time.time,
    ):

        self.path = path
        self.clock = clock

        self.limiter = LoginRateLimiter(
            path,
            clock,
        )

        self.sessions = SessionManager(
            path,
            clock,
        )

    def login(
        self,
        username: str,
        password: str,
    ) -> str:

        try:

            attempt_id = self.limiter.acquire()

            try:

                normalized = normalize_username(
                    username
                )

            except InvalidUsername:

                normalized = None

            if (
                not isinstance(password, str)
                or len(password) > MAX_PASSWORD_LENGTH
            ):

                raise AuthenticationDenied(
                    "Invalid credentials"
                )

            with connect(self.path) as connection:

                owner = connection.execute("""
                    SELECT
                        id,
                        password_hash,
                        is_active
                    FROM users
                    WHERE username = ?
                """, (normalized,)).fetchone()

            encoded = (
                owner["password_hash"]
                if owner is not None
                else _dummy_hash
            )

            verified = verify_password(
                password,
                encoded,
            )

            if (
                not verified
                or owner is None
                or owner["is_active"] != 1
            ):

                raise AuthenticationDenied(
                    "Invalid credentials"
                )

            return self._finalize_login(
                attempt_id,
                owner["id"],
                encoded,
            )

        except (
            sqlite3.Error,
            OSError,
            LoginStorageUnavailable,
            SessionDenied,
        ):

            raise AuthenticationUnavailable(
                "Secure authentication unavailable"
            ) from None

    def _finalize_login(
        self,
        attempt_id: int,
        user_id: int,
        verified_hash: str,
    ) -> str:

        token = secrets.token_urlsafe(32)

        with connect(self.path) as connection:

            connection.execute("BEGIN IMMEDIATE")

            now = int(self.clock())

            owner = connection.execute("""
                SELECT password_hash, is_active
                FROM users
                WHERE id = ?
            """, (user_id,)).fetchone()

            if (
                owner is None
                or owner["is_active"] != 1
                or not secrets.compare_digest(
                    owner["password_hash"],
                    verified_hash,
                )
            ):

                raise AuthenticationDenied(
                    "Invalid credentials"
                )

            attempt = connection.execute("""
                SELECT attempted_at, successful
                FROM login_attempts
                WHERE id = ?
            """, (attempt_id,)).fetchone()

            if (
                attempt is None
                or attempt["successful"] != 0
                or now < attempt["attempted_at"]
                or now - attempt["attempted_at"]
                    >= LOGIN_WINDOW
            ):

                raise AuthenticationDenied(
                    "Login attempt expired or invalid"
                )

            connection.execute("""
                DELETE FROM auth_sessions
                WHERE expires_at <= ?
                OR last_seen_at <= ?
                OR revoked_at IS NOT NULL
            """, (
                now,
                now - IDLE_TIMEOUT,
            ))

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
                hash_token(token),
                now,
                now + SESSION_DURATION,
                now,
            ))

            connection.execute("""
                DELETE FROM login_attempts
                WHERE id <= ?
            """, (attempt_id,))

        return token

    def authenticate(self, token: str) -> int:

        try:

            return self.sessions.validate_session(
                token
            )

        except SessionDenied:

            raise AuthenticationDenied(
                "Invalid or expired session"
            ) from None

        except (sqlite3.Error, OSError):

            raise AuthenticationUnavailable(
                "Secure authentication unavailable"
            ) from None

    def logout(self, token: str) -> None:

        try:

            self.sessions.revoke_session(token)

        except (sqlite3.Error, OSError):

            raise AuthenticationUnavailable(
                "Secure authentication unavailable"
            ) from None
