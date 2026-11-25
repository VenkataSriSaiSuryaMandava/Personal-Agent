import secrets
import threading

import anyio
import pytest

from aegis.security import public_middleware
from aegis.security.public_limits import PublicRequestLimits
from aegis.security.public_sessions import PublicSessionStore


@pytest.mark.parametrize("phase", ["acquisition", "request"])
def test_cancelled_request_releases_resources(
    monkeypatch, phase,
):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")

    gateway = secrets.token_hex(32)
    monkeypatch.setenv("AEGIS_GATEWAY_TOKEN", gateway)

    store = PublicSessionStore(capacity=1)
    limits = PublicRequestLimits()

    monkeypatch.setattr(
        public_middleware, "public_sessions", store,
    )
    monkeypatch.setattr(
        public_middleware, "public_limits", limits,
    )

    token = store.create()

    acquired = threading.Event()
    release = threading.Event()
    original_lease = store.lease

    if phase == "acquisition":
        from contextlib import contextmanager

        @contextmanager
        def delayed_lease(value):
            with original_lease(value) as path:
                acquired.set()

                if not release.wait(timeout=5):
                    raise RuntimeError("Test synchronization failed")

                yield path

        monkeypatch.setattr(store, "lease", delayed_lease)

    async def scenario():
        started = anyio.Event()
        finished = anyio.Event()
        scopes = []

        async def application(scope, receive, send):
            started.set()
            await anyio.sleep_forever()

        middleware = public_middleware.PublicStorageMiddleware(
            application,
        )

        scope = {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/api/v1/career/profile",
            "query_string": b"",
            "headers": [
                (b"host", b"localhost"),
                (b"x-aegis-gateway-token", gateway.encode()),
                (b"authorization", b"Bearer " + token.encode()),
            ],
        }

        async def receive():
            await anyio.sleep_forever()

        async def send(message):
            pytest.fail("Unexpected HTTP response")

        async def operation():
            try:
                with anyio.CancelScope() as cancel_scope:
                    scopes.append(cancel_scope)
                    await middleware(scope, receive, send)
            finally:
                finished.set()

        with anyio.fail_after(10):
            async with anyio.create_task_group() as group:
                group.start_soon(operation)

                if phase == "acquisition":
                    while not acquired.is_set():
                        await anyio.sleep(0.01)
                else:
                    await started.wait()

                scopes[0].cancel()
                release.set()
                await finished.wait()

        # No cancelled request may retain a session lease.
        entry = next(iter(store._entries.values()))
        assert entry.active_requests == 0

        # All four admission slots must be available again.
        for _ in range(4):
            assert limits.slots.acquire(blocking=False)

        assert not limits.slots.acquire(blocking=False)

        for _ in range(4):
            limits.slots.release()

    try:
        anyio.run(scenario)

        with original_lease(token) as path:
            assert path.exists()

        store.revoke(token)
        assert not path.exists()

    finally:
        release.set()
        store.close()
