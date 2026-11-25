import logging
import time
import urllib.error

from dataclasses import dataclass
from typing import Callable

from aegis.models.base import ModelProvider
from aegis.security.runtime_policy import ai_enabled
from aegis.policy import (
    Action,
    DataClass,
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


class ProviderQuotaExceeded(ProviderUnavailable):
    """The external provider rejected the request due to quota."""


class ProviderTimedOut(ProviderUnavailable):
    """The provider did not respond within the request timeout."""


class ProviderTemporarilyUnavailable(ProviderUnavailable):
    """The external provider returned a temporary service failure."""


logger = logging.getLogger(__name__)


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
        before_request: Callable[[], None] | None = None,
    ):
        self._provider = provider
        self._context = context
        self._before_request = before_request

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

        return self._complete_prompt(prompt.text)

    def complete_reviewed(self, prompt: str, classification: DataClass) -> str:
        """Only the owner-reviewed conversation service may call this entry point."""
        if not self._context.cloud_enabled or self._context.demo_mode:
            raise GatewayDenied("Reviewed conversation unavailable")
        decision = evaluate(Request(
            action=Action.CLOUD_INFERENCE,
            data=classification,
            scoped_grant=self._context.scoped_grant,
            stopped=self._context.emergency_stop,
        ))
        if decision.decision is not Decision.ALLOW:
            raise GatewayDenied(decision.reason)
        return self._complete_prompt(prompt, retry_503=True)

    def _complete_prompt(
        self,
        prompt: str,
        retry_503: bool = False,
    ) -> str:

        attempts = 2 if retry_503 else 1
        started = time.monotonic()

        for attempt in range(attempts):

            if not ai_enabled():
                raise GatewayDenied(
                    "AI is disabled in this deployment"
                )

            # Recheck permissions and reserve usage before
            # every outbound request, including retries.
            if self._before_request is not None:
                self._before_request()

            try:
                response = self._provider.complete(prompt)

            except urllib.error.HTTPError as error:
                status = error.code
                error.close()

                logger.warning(
                    "Provider HTTP failure: status=%s attempt=%s",
                    status,
                    attempt + 1,
                )

                if status == 429:
                    raise ProviderQuotaExceeded(
                        "AI provider quota exceeded"
                    ) from None

                if status == 503:
                    if (
                        attempt + 1 < attempts
                        and time.monotonic() - started < 7
                    ):
                        time.sleep(1)
                        continue

                    raise ProviderTemporarilyUnavailable(
                        "AI provider temporarily unavailable"
                    ) from None

                raise ProviderUnavailable(
                    "AI provider request failed"
                ) from None

            except TimeoutError:
                logger.warning("Provider request timed out")

                raise ProviderTimedOut(
                    "AI provider request timed out"
                ) from None

            except urllib.error.URLError as error:
                if isinstance(error.reason, TimeoutError):
                    raise ProviderTimedOut(
                        "AI provider request timed out"
                    ) from None

                logger.warning("Provider network failure")

                raise ProviderUnavailable(
                    "AI provider network unavailable"
                ) from None

            except Exception:
                # Never expose raw provider exceptions.
                logger.warning("Provider request failed")

                raise ProviderUnavailable(
                    "AI provider request failed"
                ) from None

            if (
                not isinstance(response, str)
                or not response.strip()
                or len(response) > 20000
            ):
                logger.warning("Invalid provider response")

                raise ProviderUnavailable(
                    "Invalid provider response"
                )

            return response

        raise ProviderUnavailable(
            "AI provider request failed"
        )
