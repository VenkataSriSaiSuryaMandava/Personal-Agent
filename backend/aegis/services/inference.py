import os

from aegis.models.gemini import GeminiProvider
from aegis.models.registry import (
    ACTIVE_PROVIDER,
    GEMINI_MODEL,
    create_provider,
    resolve_model,
)

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
)


ALLOWED_MODEL = GEMINI_MODEL


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

    model = resolve_model(
        ACTIVE_PROVIDER,
        requested_model,
    )

    provider = create_provider(
        ACTIVE_PROVIDER,
        model,
        factory=GeminiProvider,
    )

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
