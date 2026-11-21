from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from aegis.policy import DataClass


class PromptId(str, Enum):
    GENERAL_KNOWLEDGE = "general_knowledge"
    JOB_SEARCH_DEMO = "job_search_demo"
    PRODUCTIVITY_DEMO = "productivity_demo"


@dataclass(frozen=True)
class TrustedPrompt:
    text: str
    classification: DataClass


TRUSTED_PROMPTS = MappingProxyType({
    PromptId.GENERAL_KNOWLEDGE: TrustedPrompt(
        text="Explain how a binary search algorithm works.",
        classification=DataClass.PUBLIC,
    ),
    PromptId.JOB_SEARCH_DEMO: TrustedPrompt(
        text=(
            "Create a sample job search plan for a fictional "
            "entry-level software engineer named Alex."
        ),
        classification=DataClass.SYNTHETIC,
    ),
    PromptId.PRODUCTIVITY_DEMO: TrustedPrompt(
        text=(
            "Create an example daily productivity schedule "
            "for a fictional software engineer."
        ),
        classification=DataClass.SYNTHETIC,
    ),
})
