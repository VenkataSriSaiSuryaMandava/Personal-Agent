from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_CONTEXT_BYTES = 16000


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    user: str = Field(min_length=1, max_length=4000)
    assistant: str = Field(min_length=1, max_length=20000)


class ConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    message: str = Field(min_length=1, max_length=4000)
    history: list[Turn] = Field(max_length=3)
    classification: Literal["public", "synthetic", "personal", "sensitive", "unknown"]
    approved: bool

    @model_validator(mode="after")
    def check_context(self):
        parts = [self.message]
        for turn in self.history:
            parts.extend((turn.user, turn.assistant))
        if any(not part.strip() for part in parts):
            raise ValueError("Empty conversation item")
        if sum(len(part.encode("utf-8")) for part in parts) > MAX_CONTEXT_BYTES:
            raise ValueError("Conversation context too large")
        return self


class ConversationResponse(BaseModel):
    status: Literal["completed"] = "completed"
    provider: Literal["gemini"] = "gemini"
    model: str
    message: str
    transmitted: Literal[True] = True
    executed: Literal[False] = False
