import os
import sqlite3

from pathlib import Path

from pydantic import ValidationError

from aegis.security.gateway import GatewayDenied
from aegis.storage.database import DATABASE_PATH
from aegis.storage.settings import (
    SettingsUnavailable,
    load_settings,
)


class RuntimeControls:
    """Fail-closed cloud access checks.

    Environment configuration is a hard upper bound.
    Persistent owner settings can further restrict access.
    Neither an HTTP payload nor an AI response grants access.
    """

    def __init__(self, path: Path = DATABASE_PATH):
        self.path = path

    def require_cloud(self) -> None:
        if os.getenv("AEGIS_EMERGENCY_STOP", "0") != "0":
            raise GatewayDenied("Emergency stop is active")

        if os.getenv("AEGIS_DEMO_MODE", "0") != "0":
            raise GatewayDenied("Private cloud access unavailable")

        if os.getenv("AEGIS_CLOUD_ENABLED") != "1":
            raise GatewayDenied("Cloud inference is disabled")

        try:
            settings = load_settings(self.path).settings
        except (
            SettingsUnavailable,
            sqlite3.Error,
            OSError,
            ValidationError,
            ValueError,
            TypeError,
        ):
            raise GatewayDenied(
                "Runtime security settings unavailable"
            ) from None

        if settings.emergency_stop:
            raise GatewayDenied("Emergency stop is active")

        if not settings.cloud_enabled:
            raise GatewayDenied("Cloud access not authorized")


runtime_controls = RuntimeControls()
