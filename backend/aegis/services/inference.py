import os

from aegis.models.gemini import GeminiProvider

from aegis.schemas.inference import (
    InferenceRequest,
    InferenceResponse,
)

from aegis.security.access import limiter
from aegis.security.runtime_controls import runtime_controls

from aegis.security.gateway import (
    GatewayContext,
    GatewayDenied,
    OutboundGateway,
    ProviderUnavailable,
)


ALLOWED_MODEL = "gemini-3.1-flash-lite"


def run_inference(
    request: InferenceRequest,
    requested_model: str | None = None,
) -> InferenceResponse:

    if os.getenv("AEGIS_CLOUD_ENABLED") != "1":
        raise GatewayDenied(
            "Cloud inference is disabled"
        )

    if os.getenv("AEGIS_EMERGENCY_STOP") == "1":
        raise GatewayDenied(
            "Emergency stop is active"
        )

    runtime_controls.require_cloud()

    if request.approved is not True:
        raise GatewayDenied(
            "Explicit approval is required"
        )

    key = os.getenv("GEMINI_API_KEY", "")

    model = (
        requested_model
        if requested_model is not None
        else os.getenv("GEMINI_MODEL", ALLOWED_MODEL)
    )

    if model != ALLOWED_MODEL:
        raise GatewayDenied(
            "Model is not authorized"
        )

    if not key.strip():
        raise ProviderUnavailable(
            "AI provider is not configured"
        )

    try:

        provider = GeminiProvider(
            api_key=key,
            model=model,
        )

    except ValueError:

        raise ProviderUnavailable(
            "Invalid provider configuration"
        ) from None

    def reserve_request():
        runtime_controls.require_cloud()
        limiter.acquire()
        runtime_controls.require_cloud()

    gateway = OutboundGateway(
        provider,
        GatewayContext(
            cloud_enabled=True,
            scoped_grant=True,
            emergency_stop=False,
        ),
        before_request=reserve_request,
    )

    result = gateway.complete(
        request.prompt_id
    )

    runtime_controls.require_cloud()

    return InferenceResponse(
        model=model,
        message=result,
    )
