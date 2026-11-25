"""Server-controlled deployment capabilities."""

import os

from fastapi import HTTPException


def ai_enabled() -> bool:
    if os.getenv("AEGIS_PUBLIC_DEMO") == "1":
        return False

    if os.getenv("AEGIS_RUNTIME_MODE") == "public":
        return False

    return os.getenv("AEGIS_AI_ENABLED", "1") == "1"


def require_ai_enabled() -> None:
    if not ai_enabled():
        raise HTTPException(
            status_code=403,
            detail="AI is disabled in this deployment",
            headers={"Cache-Control": "no-store"},
        )
