import hmac
import os

from fastapi import HTTPException, Request

from aegis.security.rate_limit import (
    PersistentRateLimiter,
)


limiter = PersistentRateLimiter()


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
