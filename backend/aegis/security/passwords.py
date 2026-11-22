from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
)
from argon2.low_level import Type


MIN_PASSWORD_LENGTH = 15
MAX_PASSWORD_LENGTH = 128


class InvalidPassword(ValueError):
    """Password does not satisfy security requirements."""


_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def validate_password(password: str) -> None:

    if not isinstance(password, str):
        raise InvalidPassword("Invalid password")

    if not (
        MIN_PASSWORD_LENGTH
        <= len(password)
        <= MAX_PASSWORD_LENGTH
    ):
        raise InvalidPassword(
            "Password must contain 15 to 128 characters"
        )

    if not password.strip():
        raise InvalidPassword(
            "Password cannot contain only whitespace"
        )


def hash_password(password: str) -> str:

    validate_password(password)

    return _hasher.hash(password)


def verify_password(
    password: str,
    password_hash: str,
) -> bool:

    if not isinstance(password, str):
        return False

    if len(password) > MAX_PASSWORD_LENGTH:
        return False

    if not isinstance(password_hash, str):
        return False

    try:

        return _hasher.verify(
            password_hash,
            password,
        )

    except (
        VerificationError,
        InvalidHashError,
    ):

        return False


def needs_rehash(password_hash: str) -> bool:

    return _hasher.check_needs_rehash(
        password_hash
    )
