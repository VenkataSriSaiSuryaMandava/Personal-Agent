import os

from fastapi import APIRouter
from aegis.config import settings

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "version": settings.version,
        "stage": "api-foundation",
    }


@router.get("/api/v1/status")
def status() -> dict[str, str | bool]:

    configured = bool(
        os.getenv("GEMINI_API_KEY", "").strip()
    )

    gateway_configured = (
        len(os.getenv("AEGIS_GATEWAY_TOKEN", "")) >= 64
    )

    model = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.1-flash-lite",
    )

    enabled = (
        configured
        and gateway_configured
        and model == "gemini-3.1-flash-lite"
        and os.getenv("AEGIS_CLOUD_ENABLED") == "1"
        and os.getenv("AEGIS_EMERGENCY_STOP") != "1"
    )

    return {
        "backend": "online",
        "mode": "controlled_inference" if enabled else "preview",
        "ai_provider": (
            "gemini_configured"
            if configured
            else "not_configured"
        ),
        "database": "not_configured",
        "execution_enabled": False,
        "cloud_requests_enabled": enabled,
    }
