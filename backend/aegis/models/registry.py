"""Trusted provider definitions and construction.

The registry authorizes provider/model configuration.
The outbound gateway independently enforces data
classification, permissions and transmission policy.
"""

import os

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable

from aegis.models.base import ModelProvider
from aegis.models.gemini import GeminiProvider

from aegis.security.gateway import (
    GatewayDenied,
    ProviderUnavailable,
)


@dataclass(frozen=True)
class ProviderDefinition:
    identifier: str
    display_name: str
    implemented: bool
    authorized_models: tuple[str, ...]
    credential_env: str
    model_env: str | None
    default_model: str | None


GEMINI_MODEL = "gemini-3.1-flash-lite"

ACTIVE_PROVIDER = "gemini"

PROVIDERS = MappingProxyType({
    "gemini": ProviderDefinition(
        identifier="gemini",
        display_name="Gemini",
        implemented=True,
        authorized_models=(GEMINI_MODEL,),
        credential_env="GEMINI_API_KEY",
        model_env="GEMINI_MODEL",
        default_model=GEMINI_MODEL,
    ),
    "groq": ProviderDefinition(
        identifier="groq",
        display_name="Groq",
        implemented=False,
        authorized_models=(),
        credential_env="GROQ_API_KEY",
        model_env=None,
        default_model=None,
    ),
})

ProviderFactory = Callable[..., ModelProvider]


def get_definition(
    provider: str,
) -> ProviderDefinition:

    definition = PROVIDERS.get(provider)

    if definition is None:
        raise GatewayDenied("Unknown AI provider")

    return definition


def resolve_model(
    provider: str = ACTIVE_PROVIDER,
    requested_model: str | None = None,
) -> str:

    definition = get_definition(provider)

    if not definition.implemented:
        raise GatewayDenied("AI provider is not implemented")

    configured = definition.default_model

    if definition.model_env is not None:
        configured = os.getenv(
            definition.model_env,
            definition.default_model or "",
        )

    if configured not in definition.authorized_models:
        raise GatewayDenied("Model is not authorized")

    selected = (
        requested_model
        if requested_model is not None
        else configured
    )

    if selected not in definition.authorized_models:
        raise GatewayDenied("Model is not authorized")

    return selected


def provider_diagnostics(provider: str) -> dict:
    """Inspect configuration without outbound requests."""

    definition = get_definition(provider)

    configured = bool(
        os.getenv(definition.credential_env, "").strip()
    )

    if not definition.implemented:
        status = "not_implemented"

    elif not configured:
        status = "not_configured"

    else:
        try:
            resolve_model(provider)
            status = "configured"

        except GatewayDenied:
            status = "invalid_configuration"

    return {
        "provider": definition.identifier,
        "configured": configured,
        "implemented": definition.implemented,
        "model": definition.default_model,
        "status": status,
        "live_verified": False,
    }


def create_provider(
    provider: str = ACTIVE_PROVIDER,
    requested_model: str | None = None,
    *,
    factory: ProviderFactory | None = None,
) -> ModelProvider:
    """Create one explicitly authorized provider.

    No fallback, external discovery, arbitrary URL,
    or credential information is exposed.
    """

    model = resolve_model(provider, requested_model)

    definition = get_definition(provider)

    key = os.getenv(definition.credential_env, "")

    if not key.strip():
        raise ProviderUnavailable(
            "AI provider is not configured"
        )

    if provider != ACTIVE_PROVIDER:
        raise GatewayDenied("AI provider is not enabled")

    constructor = (
        factory
        if factory is not None
        else GeminiProvider
    )

    try:
        return constructor(
            api_key=key,
            model=model,
        )

    except ValueError:
        raise ProviderUnavailable(
            "Invalid provider configuration"
        ) from None
