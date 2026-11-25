import secrets

from aegis.security.public_limits import PublicRequestLimits


def test_creation_limit():
    limits = PublicRequestLimits()

    for _ in range(4):
        assert limits.allow_creation()

    assert not limits.allow_creation()


def test_creation_window_recovers():
    now = [1000]

    limits = PublicRequestLimits(
        clock=lambda: now[0],
    )

    for _ in range(4):
        assert limits.allow_creation()

    now[0] += 59
    assert not limits.allow_creation()

    now[0] += 1
    assert limits.allow_creation()


def test_concurrent_request_capacity():
    limits = PublicRequestLimits()

    for _ in range(4):
        assert limits.slots.acquire(blocking=False)

    assert not limits.slots.acquire(blocking=False)

    limits.slots.release()

    assert limits.slots.acquire(blocking=False)

    for _ in range(4):
        limits.slots.release()


def test_per_session_request_limit():
    limits = PublicRequestLimits()
    token = secrets.token_urlsafe(32)

    for _ in range(120):
        assert limits.allow_request(token)

    assert not limits.allow_request(token)


def test_independent_request_windows():
    limits = PublicRequestLimits()

    first = secrets.token_urlsafe(32)
    second = secrets.token_urlsafe(32)

    for _ in range(120):
        assert limits.allow_request(first)

    assert not limits.allow_request(first)
    assert limits.allow_request(second)


def test_request_window_recovers():
    now = [1000]

    limits = PublicRequestLimits(
        clock=lambda: now[0],
    )

    token = secrets.token_urlsafe(32)

    for _ in range(120):
        assert limits.allow_request(token)

    now[0] += 60

    assert limits.allow_request(token)


def test_tracking_memory_bounded():
    limits = PublicRequestLimits()

    for _ in range(64):
        assert limits.allow_request(
            secrets.token_urlsafe(32)
        )

    assert not limits.allow_request(
        secrets.token_urlsafe(32)
    )

    assert len(limits._requests) == 64


def test_expired_tracking_entries_removed():
    now = [1000]

    limits = PublicRequestLimits(
        clock=lambda: now[0],
    )

    for _ in range(64):
        assert limits.allow_request(
            secrets.token_urlsafe(32)
        )

    now[0] += 60

    assert limits.allow_request(
        secrets.token_urlsafe(32)
    )

    assert len(limits._requests) == 1


def test_invalid_token_rejected():
    limits = PublicRequestLimits()

    assert not limits.allow_request("invalid")
    assert not limits.allow_request(None)

    assert not limits._requests
