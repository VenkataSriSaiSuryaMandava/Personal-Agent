import pytest

from argon2 import PasswordHasher

from aegis.security.passwords import (
    InvalidPassword,
    hash_password,
    verify_password,
    validate_password,
    needs_rehash,
)


SYNTHETIC_PASSWORD = "Synthetic example password 2026!"


@pytest.fixture(scope="module")
def password_hash():

    return hash_password(SYNTHETIC_PASSWORD)


def test_argon2id_algorithm(password_hash):

    assert password_hash.startswith("$argon2id$")


def test_password_not_stored_as_plaintext(password_hash):

    assert SYNTHETIC_PASSWORD not in password_hash


def test_random_salts():

    first = hash_password(SYNTHETIC_PASSWORD)
    second = hash_password(SYNTHETIC_PASSWORD)

    assert first != second


def test_correct_password(password_hash):

    assert verify_password(
        SYNTHETIC_PASSWORD,
        password_hash,
    )


def test_incorrect_password(password_hash):

    assert not verify_password(
        "Incorrect synthetic password",
        password_hash,
    )


def test_case_sensitive_password(password_hash):

    assert not verify_password(
        SYNTHETIC_PASSWORD.lower(),
        password_hash,
    )


@pytest.mark.parametrize(
    "password",
    [
        "",
        "short",
        "a" * 14,
        "a" * 129,
        " " * 20,
        None,
        12345,
    ],
)
def test_invalid_password_rejected(password):

    with pytest.raises(InvalidPassword):

        validate_password(password)


@pytest.mark.parametrize("length", [15, 128])
def test_valid_password_boundaries(length):

    validate_password("a" * length)


def test_unicode_password():

    password = "Synthetic password 日本語 2026"

    encoded = hash_password(password)

    assert verify_password(password, encoded)


def test_malformed_hash():

    assert not verify_password(
        SYNTHETIC_PASSWORD,
        "invalid-hash",
    )


def test_non_string_hash():

    assert not verify_password(
        SYNTHETIC_PASSWORD,
        None,
    )


def test_non_string_password(password_hash):

    assert not verify_password(
        None,
        password_hash,
    )


def test_oversized_password(password_hash):

    assert not verify_password(
        "a" * 129,
        password_hash,
    )


def test_current_hash_needs_no_rehash(password_hash):

    assert not needs_rehash(password_hash)


def test_old_hash_requires_rehash():

    old_hasher = PasswordHasher(
        time_cost=1,
        memory_cost=8192,
        parallelism=1,
    )

    old_hash = old_hasher.hash(SYNTHETIC_PASSWORD)

    assert verify_password(
        SYNTHETIC_PASSWORD,
        old_hash,
    )

    assert needs_rehash(old_hash)
