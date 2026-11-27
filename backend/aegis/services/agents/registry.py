"""Immutable trusted capability registry.

Registration is not authorization. Runtime enforcement
must independently validate each operation.
"""

from dataclasses import dataclass
from types import MappingProxyType

from pydantic import BaseModel

from aegis.policy import Action, DataClass
from aegis.schemas.matching import MatchResult
from aegis.schemas.workflows import (
    AgentName,
    CapabilityName,
    CompanySummaryInput,
    CompanySummaryResult,
    MatchListingInput,
)


@dataclass(frozen=True)
class Capability:
    name: CapabilityName
    agent: AgentName
    version: int
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    action: Action
    data_class: DataClass
    guest_allowed: bool
    retry_safe: bool


CAPABILITIES = MappingProxyType({
    "career.company_summary": Capability(
        name="career.company_summary",
        agent="research",
        version=1,
        input_model=CompanySummaryInput,
        output_model=CompanySummaryResult,
        action=Action.LOCAL_READ,
        data_class=DataClass.PERSONAL,
        guest_allowed=True,
        retry_safe=True,
    ),
    "career.match_listing": Capability(
        name="career.match_listing",
        agent="matching",
        version=1,
        input_model=MatchListingInput,
        output_model=MatchResult,
        action=Action.LOCAL_READ,
        data_class=DataClass.PERSONAL,
        guest_allowed=True,
        retry_safe=True,
    ),
})


def resolve_capability(name: str) -> Capability:
    if not isinstance(name, str):
        raise ValueError("Invalid capability identifier")

    capability = CAPABILITIES.get(name)

    if capability is None:
        raise ValueError("Unknown capability")

    return capability
