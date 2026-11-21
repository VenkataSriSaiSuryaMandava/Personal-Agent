import hmac
import os
import time

from collections import deque
from threading import Lock

from fastapi import HTTPException, Request


class InferenceLimiter:

    def __init__(self):
        self._requests = deque()
        self._lock = Lock()

    def acquire(self):

        now = time.monotonic()

        with self._lock:

            while (
                self._requests
                and now - self._requests[0] >= 86400
            ):
                self._requests.popleft()

            recent = sum(
                now - timestamp < 60
                for timestamp in self._requests
            )

            if recent >= 3 or len(self._requests) >= 30:
                raise HTTPException(
                    status_code=429,
                    detail="Inference limit reached",
                )

            self._requests.append(now)


limiter = InferenceLimiter()


def require_gateway(request: Request):

    expected = os.getenv("AEGIS_GATEWAY_TOKEN", "")
    supplied = request.headers.get(
        "x-aegis-gateway-token", ""
    )

    if (
        len(expected) < 64
        or not hmac.compare_digest(
            expected.encode("utf-8"),
            supplied.encode("utf-8"),
        )
    ):
        raise HTTPException(
            status_code=403,
            detail="Unauthorized gateway",
        )
