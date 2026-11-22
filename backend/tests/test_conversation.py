import json
from unittest.mock import Mock

import pytest

from aegis.services import conversation as service
from aegis.security.gateway import GatewayDenied, ProviderUnavailable
from aegis.security.rate_limit import RateLimitExceeded, UsageStorageUnavailable
from aegis.schemas.conversation import ConversationRequest


@pytest.fixture
def reviewed(monkeypatch):
    monkeypatch.setenv("AEGIS_CLOUD_ENABLED", "1")
    monkeypatch.setenv("AEGIS_CUSTOM_CLOUD_ENABLED", "1")
    monkeypatch.setenv("AEGIS_EMERGENCY_STOP", "0")
    monkeypatch.setenv("AEGIS_DEMO_MODE", "0")
    monkeypatch.setenv("GEMINI_MODEL", service.ALLOWED_MODEL)
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-fixture")
    provider = Mock()
    provider.complete.return_value = "## Binary search\nWorks on sorted data."
    factory = Mock(return_value=provider)
    quota = Mock()
    monkeypatch.setattr(service, "GeminiProvider", factory)
    monkeypatch.setattr(service, "limiter", quota)
    return factory, provider, quota


def body(**changes):
    return {"message": "Explain binary search", "history": [],
            "classification": "public", "approved": True, **changes}


def request(**changes):
    return ConversationRequest.model_validate(body(**changes))


def test_reviewed_answer(reviewed):
    factory, provider, quota = reviewed
    result = service.run_conversation(request(history=[{"user": "Explain sorting", "assistant": "Sorting orders data."}]))
    assert result.transmitted is True and result.executed is False
    assert result.provider == "gemini"
    assert result.model == service.ALLOWED_MODEL
    quota.acquire.assert_called_once()
    factory.assert_called_once_with(api_key="synthetic-fixture", model=service.ALLOWED_MODEL)
    prompt = provider.complete.call_args.args[0]
    transcript = json.loads(prompt.split("Conversation transcript (JSON):\n", 1)[1])
    assert transcript["history"][0]["user"] == "Explain sorting"
    assert transcript["message"] == "Explain binary search"
    assert "synthetic-fixture" not in prompt


@pytest.mark.parametrize("changes", [
    {"approved": False}, {"classification": "personal"},
    {"classification": "sensitive"}, {"classification": "unknown"},
    {"message": "Contact example@example.invalid"},
    {"message": "password: example-value"},
    {"message": "123-45-6789"},
    {"message": "415-555-0100"},
    {"message": "4111 1111 1111 1111"},
    {"message": "\u200bHidden text"},
    {"history": [{"user": "Example", "assistant": "Contact example@example.invalid"}]},
])
def test_denied_before_provider_and_quota(reviewed, changes):
    factory, provider, quota = reviewed
    with pytest.raises(GatewayDenied):
        service.run_conversation(request(**changes))
    factory.assert_not_called()
    provider.complete.assert_not_called()
    quota.acquire.assert_not_called()


@pytest.mark.parametrize("variable,value", [
    ("AEGIS_CLOUD_ENABLED", "0"), ("AEGIS_CUSTOM_CLOUD_ENABLED", "0"),
    ("AEGIS_EMERGENCY_STOP", "1"), ("AEGIS_DEMO_MODE", "1"),
    ("GEMINI_MODEL", "unauthorized-model"),
])
def test_runtime_policy(reviewed, monkeypatch, variable, value):
    factory, provider, quota = reviewed
    monkeypatch.setenv(variable, value)
    with pytest.raises(GatewayDenied):
        service.run_conversation(request())
    factory.assert_not_called()
    provider.complete.assert_not_called()
    quota.acquire.assert_not_called()


@pytest.mark.parametrize("failure", [RateLimitExceeded, UsageStorageUnavailable])
def test_quota_failure(reviewed, failure):
    _, provider, quota = reviewed
    quota.acquire.side_effect = failure
    with pytest.raises(failure):
        service.run_conversation(request())
    provider.complete.assert_not_called()


def test_provider_error_redacted(reviewed):
    _, provider, _ = reviewed
    provider.complete.side_effect = RuntimeError("private upstream error")
    with pytest.raises(ProviderUnavailable) as exc:
        service.run_conversation(request())
    assert "private upstream error" not in str(exc.value)


def test_api_success(authenticated_environment, reviewed):
    # Fixture defaults cloud off; explicitly enable only for this mocked test.
    client = authenticated_environment[0]
    result = client.post("/api/v1/conversation", json=body())
    assert result.status_code == 200
    assert result.json()["transmitted"] is True
    assert result.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("changes", [
    {"approved": False}, {"classification": "sensitive"},
    {"message": "example@example.invalid"},
])
def test_api_policy(authenticated_environment, reviewed, changes):
    client = authenticated_environment[0]
    _, provider, _ = reviewed
    result = client.post("/api/v1/conversation", json=body(**changes))
    assert result.status_code == 403
    provider.complete.assert_not_called()
    assert "example@example.invalid" not in result.text


@pytest.mark.parametrize("changes", [
    {"approved": 1}, {"classification": "invalid"}, {"extra": "field"},
    {"message": " "}, {"message": "x" * 4001},
    {"history": [{"user": "a", "assistant": "b"}] * 4},
    {"history": [{"user": "a", "assistant": "b" * 16001}]},
])
def test_invalid_body(authenticated_environment, reviewed, changes):
    client = authenticated_environment[0]
    result = client.post("/api/v1/conversation", json=body(**changes))
    assert result.status_code == 422
    reviewed[1].complete.assert_not_called()


def test_api_authentication(authenticated_environment, reviewed):
    client = authenticated_environment[0]
    result = client.post("/api/v1/conversation", json=body(), headers={"Authorization": "Bearer invalid"})
    assert result.status_code == 401
    reviewed[1].complete.assert_not_called()


def test_api_origin(authenticated_environment, reviewed):
    client = authenticated_environment[0]
    result = client.post("/api/v1/conversation", json=body(), headers={"Origin": "https://example.invalid"})
    assert result.status_code == 403
    reviewed[1].complete.assert_not_called()


def test_duplicate_json(authenticated_environment, reviewed):
    client = authenticated_environment[0]
    result = client.post("/api/v1/conversation", content='{"message":"a","message":"b"}', headers={"Content-Type": "application/json"})
    assert result.status_code == 422
    reviewed[1].complete.assert_not_called()


def test_large_body(authenticated_environment, reviewed):
    client = authenticated_environment[0]
    result = client.post("/api/v1/conversation", content=b"x" * 98305, headers={"Content-Type": "application/json"})
    assert result.status_code == 413
    reviewed[1].complete.assert_not_called()
