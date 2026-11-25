from fastapi import APIRouter, HTTPException, Request, Depends

from aegis.api.auth import require_owner

from aegis.security.rate_limit import (
    RateLimitExceeded,
    UsageStorageUnavailable,
)

from aegis.schemas.inference import (
    InferenceRequest,
    InferenceResponse,
)

from aegis.security.gateway import (
    GatewayDenied,
    ProviderUnavailable,
)

from aegis.services.inference import run_inference


from aegis.security.runtime_policy import require_ai_enabled


router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_ai_enabled)],
)


@router.post(
    "/inference",
    response_model=InferenceResponse,
    dependencies=[Depends(require_owner)],
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

    except RateLimitExceeded:

        raise HTTPException(
            status_code=429,
            detail="Inference usage limit reached",
        ) from None

    except UsageStorageUnavailable:

        raise HTTPException(
            status_code=503,
            detail="Secure usage storage unavailable",
        ) from None

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
