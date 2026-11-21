import json
from unittest.mock import MagicMock

import pytest

from aegis.models.gemini import GeminiProvider


def make_provider():
    return GeminiProvider(
        api_key="synthetic-test-key",
        model="gemini-test-model",
    )


def mock_response(provider, payload):

    response = MagicMock()

    response.__enter__.return_value = response

    response.read.return_value = json.dumps(
        payload
    ).encode("utf-8")

    provider._opener = MagicMock()

    provider._opener.open.return_value = response


def test_missing_api_key():

    with pytest.raises(ValueError):
        GeminiProvider("", "gemini-test-model")


def test_invalid_model():

    with pytest.raises(ValueError):
        GeminiProvider(
            "synthetic-test-key",
            "https://example.com",
        )


def test_valid_response():

    provider = make_provider()

    mock_response(provider, {
        "candidates": [{
            "content": {
                "parts": [{"text": "Example model response"}]
            }
        }]
    })

    result = provider.complete("Synthetic prompt")

    assert result == "Example model response"


def test_fixed_provider_destination():

    provider = make_provider()

    mock_response(provider, {
        "candidates": [{
            "content": {
                "parts": [{"text": "Example response"}]
            }
        }]
    })

    provider.complete("Synthetic prompt")

    request = provider._opener.open.call_args.args[0]

    assert request.full_url == (
        "https://generativelanguage.googleapis.com"
        "/v1beta/models/gemini-test-model:generateContent"
    )

    assert "synthetic-test-key" not in request.full_url


def test_empty_candidates():

    provider = make_provider()

    mock_response(provider, {"candidates": []})

    with pytest.raises(RuntimeError):
        provider.complete("Synthetic prompt")


def test_empty_model_output():

    provider = make_provider()

    mock_response(provider, {
        "candidates": [{
            "content": {
                "parts": [{"text": ""}]
            }
        }]
    })

    with pytest.raises(RuntimeError):
        provider.complete("Synthetic prompt")


def test_thoughts_not_returned():

    provider = make_provider()

    mock_response(provider, {
        "candidates": [{
            "content": {
                "parts": [
                    {"text": "Internal thought", "thought": True},
                    {"text": "Final answer"},
                ]
            }
        }]
    })

    assert provider.complete("Synthetic prompt") == "Final answer"


def test_oversized_response():

    provider = make_provider()

    response = MagicMock()

    response.__enter__.return_value = response

    response.read.return_value = b"x" * 1_048_577

    provider._opener = MagicMock()

    provider._opener.open.return_value = response

    with pytest.raises(RuntimeError):
        provider.complete("Synthetic prompt")
