import io
import urllib.error
from unittest.mock import Mock

import pytest

from aegis.policy import DataClass
from aegis.security.gateway import (
    GatewayContext,
    GatewayDenied,
    OutboundGateway,
    ProviderQuotaExceeded,
    ProviderTemporarilyUnavailable,
    ProviderTimedOut,
)
from aegis.security.rate_limit import RateLimitExceeded


def http_error(status):
    return urllib.error.HTTPError(
        "https://example.invalid",
        status,
        "Synthetic provider failure",
        {},
        io.BytesIO(b"synthetic"),
    )


def make_gateway(provider, before_request):
    return OutboundGateway(
        provider,
        GatewayContext(
            cloud_enabled=True,
            scoped_grant=True,
        ),
        before_request=before_request,
    )


def complete(gateway):
    return gateway.complete_reviewed(
        "Synthetic public question",
        DataClass.PUBLIC,
    )


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(
        "aegis.security.gateway.time.sleep",
        lambda _: None,
    )


def test_retries_temporary_503():
    provider = Mock()
    provider.complete.side_effect = [
        http_error(503),
        "Successful response",
    ]
    before = Mock()

    assert complete(make_gateway(provider, before)) == (
        "Successful response"
    )

    assert provider.complete.call_count == 2
    assert before.call_count == 2


def test_stops_after_second_503():
    provider = Mock()
    provider.complete.side_effect = [
        http_error(503),
        http_error(503),
    ]
    before = Mock()

    with pytest.raises(ProviderTemporarilyUnavailable):
        complete(make_gateway(provider, before))

    assert provider.complete.call_count == 2
    assert before.call_count == 2


def test_provider_quota_not_retried():
    provider = Mock()
    provider.complete.side_effect = http_error(429)
    before = Mock()

    with pytest.raises(ProviderQuotaExceeded):
        complete(make_gateway(provider, before))

    assert provider.complete.call_count == 1


def test_timeout_not_retried():
    provider = Mock()
    provider.complete.side_effect = TimeoutError()
    before = Mock()

    with pytest.raises(ProviderTimedOut):
        complete(make_gateway(provider, before))

    assert provider.complete.call_count == 1


def test_revoked_permission_blocks_retry():
    provider = Mock()
    provider.complete.side_effect = http_error(503)

    before = Mock(side_effect=[
        None,
        GatewayDenied("Permission revoked"),
    ])

    with pytest.raises(GatewayDenied):
        complete(make_gateway(provider, before))

    assert provider.complete.call_count == 1
    assert before.call_count == 2


def test_usage_limit_blocks_retry():
    provider = Mock()
    provider.complete.side_effect = http_error(503)

    before = Mock(side_effect=[
        None,
        RateLimitExceeded("Usage limit"),
    ])

    with pytest.raises(RateLimitExceeded):
        complete(make_gateway(provider, before))

    assert provider.complete.call_count == 1
    assert before.call_count == 2
