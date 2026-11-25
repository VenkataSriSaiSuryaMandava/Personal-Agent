"""Bounded temporary visitor databases.

Public visitors reuse the existing database schema and
authentication services without sharing private data.
"""

import secrets
import time

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock

from aegis.security.owner import create_owner
from aegis.security.sessions import (
    IDLE_TIMEOUT,
    SESSION_DURATION,
    SessionDenied,
    SessionManager,
    hash_token,
    valid_token_format,
)
from aegis.storage.migrations import initialize_database
from aegis.storage.access_policy import authorize_storage


MAX_PUBLIC_SESSIONS = 8


class PublicCapacityExceeded(Exception):
    """Public session capacity is exhausted."""


@dataclass
class PublicSession:
    directory: TemporaryDirectory
    path: Path
    created_at: int
    last_seen_at: int
    active_requests: int = 0
    revoked: bool = False


class PublicSessionStore:

    def __init__(
        self,
        capacity=MAX_PUBLIC_SESSIONS,
        clock=time.time,
    ):
        if type(capacity) is not int:
            raise ValueError("Invalid public session capacity")

        if not 1 <= capacity <= MAX_PUBLIC_SESSIONS:
            raise ValueError("Invalid public session capacity")

        self.capacity = capacity
        self.clock = clock
        self._lock = RLock()
        self._entries = {}

    def _expired(self, entry, now):
        return (
            entry.revoked
            or now < entry.last_seen_at
            or now - entry.created_at >= SESSION_DURATION
            or now - entry.last_seen_at >= IDLE_TIMEOUT
        )

    def _cleanup_locked(self):
        now = int(self.clock())
        removed = 0

        for key, entry in list(self._entries.items()):
            if not self._expired(entry, now):
                continue

            entry.revoked = True

            if entry.active_requests:
                continue

            # Only remove directories created and owned
            # by this temporary session store.
            entry.directory.cleanup()
            del self._entries[key]
            removed += 1

        return removed

    def cleanup_expired(self):
        with self._lock:
            return self._cleanup_locked()

    def create(self):
        with self._lock:
            self._cleanup_locked()

            if len(self._entries) >= self.capacity:
                raise PublicCapacityExceeded(
                    "Public session capacity reached"
                )

            directory = TemporaryDirectory(
                prefix="aegis-public-",
            )

            path = Path(directory.name) / "aegis.sqlite3"

            try:
                with authorize_storage(path):
                    initialize_database(path)

                    # This account exists only inside its
                    # isolated visitor database. Its password
                    # is generated internally and never exposed.
                    create_owner(
                        "visitor",
                        secrets.token_urlsafe(48),
                        path,
                    )

                    token = SessionManager(
                        path, self.clock,
                    ).create_session(1)

                key = hash_token(token)

                if key in self._entries:
                    raise RuntimeError(
                        "Session identifier collision"
                    )

                now = int(self.clock())

                self._entries[key] = PublicSession(
                    directory=directory,
                    path=path,
                    created_at=now,
                    last_seen_at=now,
                )

                return token

            except BaseException:
                directory.cleanup()
                raise

    @contextmanager
    def lease(self, token):
        if not valid_token_format(token):
            raise SessionDenied("Invalid public session")

        key = hash_token(token)

        with self._lock:
            self._cleanup_locked()

            entry = self._entries.get(key)

            if (
                entry is None
                or entry.revoked
                or self._expired(entry, int(self.clock()))
            ):
                raise SessionDenied(
                    "Invalid or expired public session"
                )

            # Validate using the same session service
            # as the private application.
            with authorize_storage(entry.path):
                user_id = SessionManager(
                    entry.path, self.clock,
                ).validate_session(token)

            if user_id != 1:
                raise SessionDenied(
                    "Invalid public account"
                )

            entry.last_seen_at = int(self.clock())
            entry.active_requests += 1

        try:
            yield entry.path

        finally:
            with self._lock:
                entry.active_requests -= 1
                self._cleanup_locked()

    def revoke(self, token):
        if not valid_token_format(token):
            return

        key = hash_token(token)

        with self._lock:
            entry = self._entries.get(key)

            if entry is not None:
                entry.revoked = True

                with authorize_storage(entry.path):
                    SessionManager(
                        entry.path, self.clock,
                    ).revoke_session(token)

            self._cleanup_locked()

    def close(self):
        with self._lock:
            for entry in self._entries.values():
                entry.revoked = True

            self._cleanup_locked()


public_sessions = PublicSessionStore()
