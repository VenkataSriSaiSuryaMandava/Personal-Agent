"""Runtime checks for registered local operations."""

import os

from aegis.policy import Action
from aegis.services.agents.registry import resolve_capability
from aegis.security.request_storage import public_runtime


class CapabilityDenied(Exception):
    pass


def authorize_local_capability(
    name: str,
    *,
    emergency_stop: bool,
    scoped_grant: bool,
):
    capability = resolve_capability(name)

    if scoped_grant is not True:
        raise CapabilityDenied("Permission required")

    if (
        emergency_stop is not False
        or os.getenv("AEGIS_EMERGENCY_STOP", "0") != "0"
    ):
        raise CapabilityDenied("Emergency stop is active")

    guest = (
        public_runtime()
        or os.getenv("AEGIS_PUBLIC_DEMO") == "1"
    )

    if guest and not capability.guest_allowed:
        raise CapabilityDenied("Capability unavailable")

    if capability.action is not Action.LOCAL_READ:
        raise CapabilityDenied("External execution unavailable")

    return capability
