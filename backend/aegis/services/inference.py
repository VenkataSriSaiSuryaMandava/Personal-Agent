import os

from aegis.models.gemini import GeminiProvider
from aegis.schemas.inference import (
    InferenceRequest,
    InferenceResponse,
)
from aegis.security.gateway import (
    GatewayContext,
    GatewayDenied,
    OutboundGateway,
    ProviderUnavailable,
)


def run_inference(
    request: InferenceRequest,
) -> InferenceResponse:

    if os.getenv("AEGIS_CLOUD_ENABLED") != "1":
        raise GatewayDenied("Cloud inference is disabled")

    if os.getenv("AEGIS_EMERGENCY_STOP") == "1":
        raise GatewayDenied("Emergency stop is active")

    key = os.getenv("GEMINI_API_KEY", "")
    model = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.1-flash-lite",
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

    gateway = OutboundGateway(
        provider,
        GatewayContext(
            cloud_enabled=True,
            scoped_grant=request.approved is True,
            emergency_stop=False,
        ),
    )

    result = gateway.complete(request.prompt_id)

    return InferenceResponse(
        model=model,
        message=result,
    )
