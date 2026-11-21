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
    return {
        "backend": "online",
        "mode": "preview",
        "ai_provider": "not_configured",
        "database": "not_configured",
        "execution_enabled": False,
        "cloud_requests_enabled": False,
    }
