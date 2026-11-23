from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from aegis.api import auth, conversation
from aegis.api import settings as settings_api
from aegis.api import chat, health, inference
from aegis.config import settings


app = FastAPI(
    title=settings.name,
    version=settings.version,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "127.0.0.1",
        "localhost",
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
