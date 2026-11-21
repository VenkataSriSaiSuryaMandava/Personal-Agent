from dataclasses import dataclass

from aegis.models.base import ModelProvider
from aegis.policy import (
    Action,
    Decision,
    Request,
    evaluate,
)
from aegis.security.prompts import (
    PromptId,
    TRUSTED_PROMPTS,
)


class GatewayDenied(Exception):
    """The requested operation violates security policy."""


class ProviderUnavailable(Exception):
    """The authorized provider could not complete the request."""


@dataclass(frozen=True)
class GatewayContext:
    # Must originate from trusted server-side configuration.
    # Never populate these values from an HTTP request or LLM.
    cloud_enabled: bool = False
    scoped_grant: bool = False
    emergency_stop: bool = False
    demo_mode: bool = False


class OutboundGateway:

    def __init__(
        self,
        provider: ModelProvider,
        context: GatewayContext,
    ):
        self._provider = provider
        self._context = context

    def complete(self, prompt_id: PromptId) -> str:

        if not self._context.cloud_enabled:
            raise GatewayDenied(
                "Cloud inference is disabled"
            )

        if not isinstance(prompt_id, PromptId):
            raise GatewayDenied(
                "Unknown or untrusted prompt"
            )

        prompt = TRUSTED_PROMPTS.get(prompt_id)

        if prompt is None:
            raise GatewayDenied(
                "Unknown or untrusted prompt"
            )

        decision = evaluate(
            Request(
                action=Action.CLOUD_INFERENCE,
                data=prompt.classification,
                scoped_grant=self._context.scoped_grant,
                stopped=self._context.emergency_stop,
                demo=self._context.demo_mode,
            )
        )

        if decision.decision is not Decision.ALLOW:
            raise GatewayDenied(decision.reason)

        try:
            response = self._provider.complete(prompt.text)
        except Exception:
            # Do not expose raw provider errors, keys or prompts.
            raise ProviderUnavailable(
                "AI provider request failed"
            ) from None

        if (
            not isinstance(response, str)
            or not response.strip()
            or len(response) > 20000
        ):
            raise ProviderUnavailable(
                "Invalid provider response"
            )

        # Provider output is untrusted text.
        # It must not be executed as a command.
        return response
