import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from aegis.schemas.auth import (
    LoginRequest,
    LoginResponse,
    SessionResponse,
    LogoutResponse,
)

from aegis.security.access import require_gateway

from aegis.security.authentication import (
    AuthenticationService,
    AuthenticationDenied,
    AuthenticationUnavailable,
)

from aegis.security.login_limit import (
    LoginLimitExceeded,
    LOGIN_WINDOW,
)

from aegis.security.sessions import (
    SESSION_DURATION,
    valid_token_format,
)


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["authentication"],
)

service = AuthenticationService()

MAX_LOGIN_BODY = 4096

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
}


def deny(status_code: int, message: str):

    raise HTTPException(
        status_code=status_code,
        detail=message,
        headers=SECURITY_HEADERS,
    )


def trusted_request(request: Request) -> None:

    if request.headers.get("origin") is not None:

        deny(403, "Request denied")

    require_gateway(request)


def read_session_token(request: Request) -> str:

    authorization = request.headers.get(
        "authorization",
        "",
    )

    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not valid_token_format(token)
    ):

        deny(401, "Authentication required")

    return token


async def read_login_request(
    request: Request,
) -> LoginRequest:

    content_type = request.headers.get(
        "content-type",
        "",
    ).split(";")[0].strip().lower()

    if content_type != "application/json":

        deny(415, "Unsupported content type")

    body = bytearray()

    async for chunk in request.stream():

        if len(body) + len(chunk) > MAX_LOGIN_BODY:

            deny(413, "Request too large")

        body.extend(chunk)

    try:

        payload = json.loads(body)

        return LoginRequest.model_validate(payload)

    except (
        ValueError,
        UnicodeError,
        ValidationError,
        RecursionError,
    ):

        deny(422, "Invalid request")


@router.post("/login")
async def login(request: Request):

    trusted_request(request)

    payload = await read_login_request(request)

    try:

        token = await run_in_threadpool(
            service.login,
            payload.username,
            payload.password,
        )

    except AuthenticationDenied:

        deny(401, "Invalid credentials")

    except LoginLimitExceeded:

        raise HTTPException(
            status_code=429,
            detail="Login attempt limit reached",
            headers={
                **SECURITY_HEADERS,
                "Retry-After": str(LOGIN_WINDOW),
            },
        )

    except AuthenticationUnavailable:

        deny(503, "Authentication unavailable")

    result = LoginResponse(
        session_token=token,
        expires_in=SESSION_DURATION,
    )

    return JSONResponse(
        content=result.model_dump(),
        headers=SECURITY_HEADERS,
    )


@router.get("/session")
def session(request: Request):

    trusted_request(request)

    token = read_session_token(request)

    try:

        service.authenticate(token)

    except AuthenticationDenied:

        deny(401, "Invalid or expired session")

    except AuthenticationUnavailable:

        deny(503, "Authentication unavailable")

    return JSONResponse(
        content=SessionResponse().model_dump(),
        headers=SECURITY_HEADERS,
    )


@router.post("/logout")
def logout(request: Request):

    trusted_request(request)

    token = read_session_token(request)

    try:

        service.logout(token)

    except AuthenticationUnavailable:

        deny(503, "Authentication unavailable")

    return JSONResponse(
        content=LogoutResponse().model_dump(),
        headers=SECURITY_HEADERS,
    )
