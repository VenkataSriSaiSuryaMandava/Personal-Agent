import asyncio
import logging

from contextlib import asynccontextmanager

from starlette.concurrency import run_in_threadpool

from aegis.security.public_sessions import public_sessions
from aegis.security.request_storage import public_runtime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from aegis.api import auth, conversation, conversation_history
from aegis.api import career, discovery, workspaces
from aegis.api import settings as settings_api
from aegis.api import chat, health, inference
from aegis.config import settings
from aegis.security.public_middleware import PublicStorageMiddleware


async def cleanup_public_sessions():
    while True:
        await asyncio.sleep(60)

        try:
            await run_in_threadpool(
                public_sessions.cleanup_expired,
            )
        except OSError:
            logging.getLogger(__name__).warning(
                "Public session cleanup unavailable"
            )


@asynccontextmanager
async def lifespan(app):
    task = None

    if public_runtime():
        task = asyncio.create_task(
            cleanup_public_sessions()
        )

    try:
        yield

    finally:
        if task is not None:
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            await run_in_threadpool(
                public_sessions.close,
            )


app = FastAPI(
    lifespan=lifespan,
    title=settings.name,
    version=settings.version,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(PublicStorageMiddleware)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "127.0.0.1",
        "localhost",
        "backend",
        "guest-backend",
        "testserver",
    ],
)


@app.exception_handler(RequestValidationError)
async def validation_error(
    request: Request,
    exc: RequestValidationError,
):
    # Avoid echoing potentially private input in errors.
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request"},
    )


app.include_router(health.router)
app.include_router(chat.router)

app.include_router(inference.router)

app.include_router(auth.router)

app.include_router(conversation.router)

app.include_router(settings_api.router)

app.include_router(conversation_history.router)

app.include_router(workspaces.router)

app.include_router(career.router)

app.include_router(discovery.router)
