import pytest

from aegis.security.gateway import (
    GatewayContext,
    GatewayDenied,
    OutboundGateway,
    ProviderUnavailable,
)
from aegis.security.prompts import PromptId


class FakeProvider:

    def __init__(self, response="Example AI response"):
        self.calls = []
        self.response = response

    def complete(self, prompt):
        self.calls.append(prompt)
        return self.response


class FailingProvider:

    def complete(self, prompt):
        raise RuntimeError("Synthetic private error")


def test_cloud_disabled_by_default():
    provider = FakeProvider()

    gateway = OutboundGateway(
        provider,
        GatewayContext(),
    )

    with pytest.raises(GatewayDenied):
        gateway.complete(PromptId.GENERAL_KNOWLEDGE)

    assert provider.calls == []


def test_permission_required():
    provider = FakeProvider()

    gateway = OutboundGateway(
        provider,
        GatewayContext(cloud_enabled=True),
    )

    with pytest.raises(GatewayDenied):
        gateway.complete(PromptId.GENERAL_KNOWLEDGE)

    assert provider.calls == []


def test_authorized_public_prompt():
    provider = FakeProvider()

    gateway = OutboundGateway(
        provider,
        GatewayContext(
            cloud_enabled=True,
            scoped_grant=True,
        ),
    )

    response = gateway.complete(
        PromptId.GENERAL_KNOWLEDGE
    )

    assert response == "Example AI response"
    assert len(provider.calls) == 1
    assert "binary search" in provider.calls[0]


def test_emergency_stop_blocks_provider():
    provider = FakeProvider()

    gateway = OutboundGateway(
        provider,
        GatewayContext(
            cloud_enabled=True,
            scoped_grant=True,
            emergency_stop=True,
        ),
    )

    with pytest.raises(GatewayDenied):
        gateway.complete(PromptId.GENERAL_KNOWLEDGE)

    assert provider.calls == []


def test_demo_blocks_non_synthetic_prompt():
    provider = FakeProvider()

    gateway = OutboundGateway(
        provider,
        GatewayContext(
            cloud_enabled=True,
            scoped_grant=True,
            demo_mode=True,
        ),
    )

    with pytest.raises(GatewayDenied):
        gateway.complete(PromptId.GENERAL_KNOWLEDGE)

    assert provider.calls == []


def test_demo_allows_synthetic_prompt():
    provider = FakeProvider()

    gateway = OutboundGateway(
        provider,
        GatewayContext(
            cloud_enabled=True,
            scoped_grant=True,
            demo_mode=True,
        ),
    )

    response = gateway.complete(
        PromptId.JOB_SEARCH_DEMO
    )

    assert response == "Example AI response"
    assert len(provider.calls) == 1


def test_arbitrary_input_is_rejected():
    provider = FakeProvider()

    gateway = OutboundGateway(
        provider,
        GatewayContext(
            cloud_enabled=True,
            scoped_grant=True,
        ),
    )

    with pytest.raises(GatewayDenied):
        gateway.complete("Untrusted personal information")

    assert provider.calls == []


def test_provider_error_is_redacted():
    gateway = OutboundGateway(
        FailingProvider(),
        GatewayContext(
            cloud_enabled=True,
            scoped_grant=True,
        ),
    )

    with pytest.raises(ProviderUnavailable) as error:
        gateway.complete(PromptId.GENERAL_KNOWLEDGE)

    assert str(error.value) == "AI provider request failed"
    assert "Synthetic private error" not in str(error.value)


@pytest.mark.parametrize("response", [
    "",
    "   ",
    None,
    "x" * 20001,
])
def test_invalid_provider_response(response):
    gateway = OutboundGateway(
        FakeProvider(response),
        GatewayContext(
            cloud_enabled=True,
            scoped_grant=True,
        ),
    )

    with pytest.raises(ProviderUnavailable):
        gateway.complete(PromptId.GENERAL_KNOWLEDGE)
