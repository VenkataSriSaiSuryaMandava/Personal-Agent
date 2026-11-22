import re
import time

from pathlib import Path

from aegis.security.passwords import hash_password

from aegis.storage.database import (
    DATABASE_PATH,
    connect,
)


class OwnerAlreadyExists(Exception):
    """The application already has an owner."""


class InvalidUsername(ValueError):
    """The username does not satisfy requirements."""


def normalize_username(username: str) -> str:

    if not isinstance(username, str):
        raise InvalidUsername("Invalid username")

    username = username.strip().lower()

    if not re.fullmatch(
        r"[a-z0-9][a-z0-9_.-]{2,31}",
        username,
    ):
        raise InvalidUsername(
            "Username must contain 3 to 32 "
            "valid characters"
        )

    return username


def owner_exists(
    path: Path = DATABASE_PATH,
) -> bool:

    with connect(path) as connection:

        return connection.execute(
            "SELECT 1 FROM users WHERE id = 1"
        ).fetchone() is not None


def create_owner(
    username: str,
    password: str,
    path: Path = DATABASE_PATH,
) -> None:

    username = normalize_username(username)

    if owner_exists(path):

        raise OwnerAlreadyExists(
            "An owner account already exists"
        )

    password_hash = hash_password(password)

    with connect(path) as connection:

        connection.execute("BEGIN IMMEDIATE")

        existing = connection.execute(
            "SELECT 1 FROM users WHERE id = 1"
        ).fetchone()

        if existing is not None:

            raise OwnerAlreadyExists(
                "An owner account already exists"
            )

        connection.execute("""
            INSERT INTO users (
                id,
                username,
                password_hash,
                created_at,
                is_active
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            1,
            username,
            password_hash,
            int(time.time()),
            1,
        ))


class OwnerNotConfigured(Exception):
    """No owner account has been configured."""


def reset_owner_password(
    password: str,
    path: Path = DATABASE_PATH,
) -> None:

    if not owner_exists(path):

        raise OwnerNotConfigured(
            "Owner account is not configured"
        )

    password_hash = hash_password(password)

    with connect(path) as connection:

        connection.execute("BEGIN IMMEDIATE")

        cursor = connection.execute("""
            UPDATE users
            SET password_hash = ?
            WHERE id = 1
            AND is_active = 1
        """, (password_hash,))

        if cursor.rowcount != 1:

            raise OwnerNotConfigured(
                "Active owner account unavailable"
            )

        connection.execute("""
            UPDATE auth_sessions
            SET revoked_at = ?
            WHERE user_id = 1
            AND revoked_at IS NULL
        """, (int(time.time()),))

        connection.execute("""
            DELETE FROM login_attempts
        """)
