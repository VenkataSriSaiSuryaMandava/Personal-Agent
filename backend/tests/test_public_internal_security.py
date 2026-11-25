import pytest

from aegis.models.gemini import GeminiProvider
from aegis.security.gateway import (
    GatewayContext,
    GatewayDenied,
    OutboundGateway,
)
from aegis.storage.backup import create_backup


@pytest.fixture
def public_mode(monkeypatch):
    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")
    monkeypatch.setenv("AEGIS_AI_ENABLED", "1")


def test_public_backup_denied_before_filesystem_access(
    public_mode, tmp_path,
):
    source = tmp_path / "missing.sqlite3"
    destination = tmp_path / "backup" / "copy.sqlite3"

    with pytest.raises(PermissionError):
        create_backup(source, destination)

    assert not destination.parent.exists()


def test_public_internal_gateway_denied(public_mode):
    class Provider:
        def complete(self, prompt):
            pytest.fail("Provider was called")

    gateway = OutboundGateway(
        Provider(),
        GatewayContext(
            cloud_enabled=True,
            scoped_grant=True,
        ),
    )

    with pytest.raises(GatewayDenied):
        gateway._complete_prompt("Synthetic test")


def test_public_direct_provider_denied(
    public_mode, monkeypatch,
):
    provider = GeminiProvider(
        api_key="synthetic-test-key",
        model="gemini-test",
    )

    def forbidden(*args, **kwargs):
        pytest.fail("Outbound request attempted")

    monkeypatch.setattr(
        provider._opener,
        "open",
        forbidden,
    )

    with pytest.raises(
        RuntimeError,
        match="AI is disabled",
    ):
        provider.complete("Synthetic test")
