"""Pure policy evaluation; never executes actions or grants permissions."""
from dataclasses import dataclass
from enum import Enum


class DataClass(str, Enum):
    PUBLIC = "public"
    SYNTHETIC = "synthetic"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    UNKNOWN = "unknown"


class Action(str, Enum):
    CLOUD_INFERENCE = "cloud_inference"
    LOCAL_READ = "local_read"
    LOCAL_WRITE = "local_write"
    PUBLIC_RESEARCH = "public_research"
    EXTERNAL_DISCLOSURE = "external_disclosure"
    SEND_MESSAGE = "send_message"
    SUBMIT_APPLICATION = "submit_application"
    TERMINAL = "terminal"
    HIGH_RISK = "high_risk"


class Decision(str, Enum):
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"
    ALLOW = "allow"


@dataclass(frozen=True)
class Request:
    action: Action
    data: DataClass = DataClass.UNKNOWN
    # These values must originate from trusted runtime policy, never model output.
    scoped_grant: bool = False
    stopped: bool = False
    demo: bool = False


@dataclass(frozen=True)
class Result:
    decision: Decision
    reason: str


def evaluate(request: Request) -> Result:
    if request.stopped:
        return Result(Decision.DENY, "Emergency stop is active")
    if request.data is DataClass.UNKNOWN:
        return Result(Decision.DENY, "Unclassified data")
    if request.demo and (request.data is not DataClass.SYNTHETIC or request.action is not Action.CLOUD_INFERENCE):
        return Result(Decision.DENY, "Demo supports synthetic inference only")
    if request.action is Action.CLOUD_INFERENCE and request.data not in {DataClass.PUBLIC, DataClass.SYNTHETIC}:
        return Result(Decision.DENY, "Private data cannot be sent to cloud AI")
    if not request.scoped_grant:
        return Result(Decision.DENY, "No scoped permission")
    if request.action in {Action.EXTERNAL_DISCLOSURE, Action.SEND_MESSAGE, Action.SUBMIT_APPLICATION, Action.TERMINAL, Action.HIGH_RISK}:
        return Result(Decision.APPROVAL_REQUIRED, "Explicit action approval is required")
    if request.data is DataClass.SENSITIVE:
        return Result(Decision.APPROVAL_REQUIRED, "Sensitive local access requires approval")
    return Result(Decision.ALLOW, "Within granted scope")
