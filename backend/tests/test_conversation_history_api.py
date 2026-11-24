import pytest

from fastapi.testclient import TestClient

from aegis.api import conversation
from aegis.main import app

from aegis.schemas.conversation import ConversationResponse
from aegis.security.gateway import ProviderUnavailable

from aegis.storage.settings import load_settings, save_settings
from aegis.storage.conversations import list_conversations


BASE = "/api/v1/conversations"
GENERATE = "/api/v1/conversation"


@pytest.fixture
def environment(
    authenticated_environment,
    monkeypatch,
):
    client, auth, token, path, now = (
        authenticated_environment
    )

    def mock_response(payload):
        return ConversationResponse(
            model="gemini-3.1-flash-lite",
            message="Synthetic assistant response",
        )

    monkeypatch.setattr(
        conversation,
        "run_conversation",
        mock_response,
    )

    return client, path


def retention(path, enabled):
    current = load_settings(path)

    save_settings(
        current.settings.model_copy(
            update={
                "retain_conversations": enabled,
            }
        ),
        current.revision,
        path,
    )


def generate(client, **changes):
    return client.post(
        GENERATE,
        json={
            "message": "Explain binary search",
            "history": [],
            "classification": "synthetic",
            "approved": True,
            "persist": True,
            **changes,
        },
    )


def create_chat(client, path):
    retention(path, True)

    response = generate(client)

    assert response.status_code == 200
    assert response.json()["persisted"] is True

    return response.json()["conversation_id"]


def test_disabled_retention(environment):
    client, path = environment

    response = generate(client)

    assert response.status_code == 200
    assert response.json()["persisted"] is False
    assert response.json()["persistence_status"] == (
        "retention_disabled"
    )

    assert list_conversations(1, path=path) == []


def test_create_and_reopen(environment):
    client, path = environment

    identifier = create_chat(client, path)

    response = client.get(BASE)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"

    assert response.json()["conversations"][0]["id"] == (
        identifier
    )

    detail = client.get(f"{BASE}/{identifier}")

    assert detail.status_code == 200
    assert len(detail.json()["turns"]) == 1


def test_append(environment):
    client, path = environment

    identifier = create_chat(client, path)

    response = generate(
        client,
        conversation_id=identifier,
        expected_turn_count=1,
    )

    assert response.status_code == 200
    assert response.json()["persisted"] is True

    result = client.get(
        f"{BASE}/{identifier}"
    ).json()

    assert len(result["turns"]) == 2


def test_conflicting_turn_rejected(environment):
    client, path = environment

    identifier = create_chat(client, path)

    response = generate(
        client,
        conversation_id=identifier,
        expected_turn_count=0,
    )

    assert response.status_code == 409


def test_rename_and_delete(environment):
    client, path = environment

    identifier = create_chat(client, path)

    route = f"{BASE}/{identifier}"

    assert client.patch(
        route,
        json={"title": "Algorithms"},
    ).status_code == 200

    assert client.get(route).json()["title"] == (
        "Algorithms"
    )

    assert client.delete(route).status_code == 200
    assert client.get(route).status_code == 404


def test_disabled_retention_keeps_existing_history(environment):
    client, path = environment

    identifier = create_chat(client, path)

    retention(path, False)

    assert client.get(
        f"{BASE}/{identifier}"
    ).status_code == 200

    assert generate(
        client,
        conversation_id=identifier,
        expected_turn_count=1,
    ).status_code == 409

    assert client.delete(
        f"{BASE}/{identifier}"
    ).status_code == 200


def test_nonpersistent_request(environment):
    client, path = environment

    retention(path, True)

    response = generate(
        client,
        persist=False,
    )

    assert response.status_code == 200
    assert list_conversations(1, path=path) == []


def test_failed_generation_not_saved(
    environment,
    monkeypatch,
):
    client, path = environment

    retention(path, True)

    def failure(payload):
        raise ProviderUnavailable("Synthetic failure")

    monkeypatch.setattr(
        conversation,
        "run_conversation",
        failure,
    )

    assert generate(client).status_code == 503
    assert list_conversations(1, path=path) == []


def test_retention_revoked_during_generation(
    environment,
    monkeypatch,
):
    client, path = environment

    retention(path, True)

    def response_after_revocation(payload):
        retention(path, False)

        return ConversationResponse(
            model="gemini-3.1-flash-lite",
            message="Synthetic response",
        )

    monkeypatch.setattr(
        conversation,
        "run_conversation",
        response_after_revocation,
    )

    response = generate(client)

    assert response.status_code == 200
    assert response.json()["persisted"] is False
    assert list_conversations(1, path=path) == []


def test_gateway_and_session_required(environment):
    client, path = environment

    with TestClient(app) as anonymous:
        assert anonymous.get(BASE).status_code == 403

    with TestClient(
        app,
        headers={
            "x-aegis-gateway-token": (
                client.headers["x-aegis-gateway-token"]
            )
        },
    ) as anonymous:
        assert anonymous.get(BASE).status_code == 401


def test_foreign_origin_rejected(environment):
    client, path = environment

    assert client.get(
        BASE,
        headers={"origin": "https://example.invalid"},
    ).status_code == 403


@pytest.mark.parametrize("query", [
    "limit=0",
    "limit=101",
    "limit=1&limit=2",
    "offset=-1",
    "unknown=1",
])
def test_invalid_query(environment, query):
    client, path = environment

    assert client.get(
        BASE + "?" + query
    ).status_code == 422


def test_user_id_cannot_be_supplied(environment):
    client, path = environment

    assert generate(
        client,
        user_id=2,
    ).status_code == 422


def test_invalid_conversation_id(environment):
    client, path = environment

    assert client.get(
        BASE + "/invalid"
    ).status_code == 422


def test_revoked_session(environment):
    client, path = environment

    assert client.post(
        "/api/v1/auth/logout"
    ).status_code == 200

    assert client.get(BASE).status_code == 401
