from fastapi import APIRouter, HTTPException, Request

from aegis.schemas.inference import (
    InferenceRequest,
    InferenceResponse,
)
from aegis.security.gateway import (
    GatewayDenied,
    ProviderUnavailable,
)
from aegis.services.inference import run_inference


router = APIRouter(prefix="/api/v1")


@router.post(
    "/inference",
    response_model=InferenceResponse,
)
def inference(
    payload: InferenceRequest,
    request: Request,
) -> InferenceResponse:

    if request.headers.get("origin") is not None:
        raise HTTPException(
            status_code=403,
            detail="Direct browser access is disabled",
        )

    content_type = request.headers.get(
        "content-type", ""
    ).split(";")[0].strip().lower()

    if content_type != "application/json":
        raise HTTPException(
            status_code=415,
            detail="JSON request required",
        )

    try:
        return run_inference(payload)

    except GatewayDenied:
        raise HTTPException(
            status_code=403,
            detail="Inference denied by security policy",
        ) from None

    except ProviderUnavailable:
        raise HTTPException(
            status_code=503,
            detail="AI provider unavailable",
        ) from None
