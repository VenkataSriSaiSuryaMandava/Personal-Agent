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
    persist: bool = False
    conversation_id: str | None = Field(
        default=None,
        min_length=36,
        max_length=36,
    )
    expected_turn_count: int = Field(
        default=0,
        ge=0,
        le=1000000,
    )

    @model_validator(mode="after")
    def check_context(self):
        if not self.persist and (
            self.conversation_id is not None
            or self.expected_turn_count != 0
        ):
            raise ValueError("Invalid persistence request")

        if (
            self.conversation_id is None
            and self.expected_turn_count != 0
        ):
            raise ValueError("Invalid conversation state")

        if self.conversation_id is not None:
            from uuid import UUID

            if str(UUID(self.conversation_id)) != self.conversation_id:
                raise ValueError("Invalid conversation ID")

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
