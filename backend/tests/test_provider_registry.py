from unittest.mock import Mock

import pytest

from aegis.models.registry import (
    ACTIVE_PROVIDER,
    GEMINI_MODEL,
    PROVIDERS,
    create_provider,
    get_definition,
    provider_diagnostics,
    resolve_model,
)

from aegis.security.gateway import (
    GatewayDenied,
    ProviderUnavailable,
)


@pytest.fixture(autouse=True)
def clean_provider_environment(monkeypatch):
    monkeypatch.delenv(
        "GEMINI_API_KEY", raising=False
    )
    monkeypatch.delenv(
        "GEMINI_MODEL", raising=False
    )
    monkeypatch.delenv(
        "GROQ_API_KEY", raising=False
    )


def test_gemini_only_active_provider():
    assert ACTIVE_PROVIDER == "gemini"
    assert get_definition("gemini").implemented
    assert not get_definition("groq").implemented


def test_default_model():
    assert resolve_model("gemini") == GEMINI_MODEL


def test_registry_is_immutable():
    with pytest.raises(TypeError):
        PROVIDERS["other"] = None


@pytest.mark.parametrize("provider", [
    "groq",
    "ollama",
    "openai",
    "unknown",
    "https://example.invalid",
    "",
])
def test_unsupported_providers_denied(provider):
    constructor = Mock()

    with pytest.raises(GatewayDenied):
        create_provider(
            provider,
            factory=constructor,
        )

    constructor.assert_not_called()


@pytest.mark.parametrize("model", [
    "",
    "unknown-model",
    "gemini-unauthorized",
    "../other",
    "https://example.invalid",
])
def test_unauthorized_models_denied(model):
    constructor = Mock()

    with pytest.raises(GatewayDenied):
        create_provider(
            "gemini",
            model,
            factory=constructor,
        )

    constructor.assert_not_called()


def test_missing_credentials(monkeypatch):
    constructor = Mock()

    with pytest.raises(ProviderUnavailable):
        create_provider(
            "gemini",
            factory=constructor,
        )

    constructor.assert_not_called()


def test_whitespace_credentials(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "   ")

    with pytest.raises(ProviderUnavailable):
        create_provider("gemini")


def test_authorized_provider_construction(monkeypatch):
    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "synthetic-test-value",
    )

    constructor = Mock()

    result = create_provider(
        "gemini",
        factory=constructor,
    )

    constructor.assert_called_once_with(
        api_key="synthetic-test-value",
        model=GEMINI_MODEL,
    )

    assert result is constructor.return_value

    result.complete.assert_not_called()


def test_invalid_environment_model(monkeypatch):
    monkeypatch.setenv(
        "GEMINI_MODEL",
        "unapproved-model",
    )

    with pytest.raises(GatewayDenied):
        resolve_model("gemini")


def test_explicit_model_cannot_bypass_invalid_configuration(
    monkeypatch,
):
    monkeypatch.setenv(
        "GEMINI_MODEL",
        "unapproved-model",
    )

    with pytest.raises(GatewayDenied):
        resolve_model("gemini", GEMINI_MODEL)


def test_safe_constructor_error(monkeypatch):
    synthetic = "synthetic-secret-value"

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        synthetic,
    )

    constructor = Mock(
        side_effect=ValueError(synthetic),
    )

    with pytest.raises(ProviderUnavailable) as error:
        create_provider(
            "gemini",
            factory=constructor,
        )

    assert synthetic not in str(error.value)


def test_diagnostics_missing_key():
    status = provider_diagnostics("gemini")

    assert status["status"] == "not_configured"
    assert status["configured"] is False
    assert status["live_verified"] is False


def test_diagnostics_never_expose_key(monkeypatch):
    synthetic = "synthetic-private-value"

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        synthetic,
    )

    status = provider_diagnostics("gemini")

    assert status["status"] == "configured"
    assert status["model"] == GEMINI_MODEL
    assert status["live_verified"] is False
    assert synthetic not in str(status)


def test_diagnostics_invalid_configuration(monkeypatch):
    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "synthetic",
    )

    monkeypatch.setenv(
        "GEMINI_MODEL",
        "unauthorized",
    )

    assert provider_diagnostics(
        "gemini"
    )["status"] == "invalid_configuration"


def test_no_implicit_groq_fallback(monkeypatch):
    monkeypatch.setenv(
        "GROQ_API_KEY",
        "synthetic",
    )

    constructor = Mock()

    with pytest.raises(ProviderUnavailable):
        create_provider(
            "gemini",
            factory=constructor,
        )

    constructor.assert_not_called()

    status = provider_diagnostics("groq")

    assert status["implemented"] is False
    assert status["status"] == "not_implemented"


def test_diagnostics_do_not_construct_provider(
    monkeypatch,
):
    constructor = Mock()

    monkeypatch.setattr(
        "aegis.models.registry.GeminiProvider",
        constructor,
    )

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "synthetic",
    )

    provider_diagnostics("gemini")

    constructor.assert_not_called()
