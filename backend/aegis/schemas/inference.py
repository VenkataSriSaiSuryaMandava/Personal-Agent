from typing import Literal

from pydantic import BaseModel, ConfigDict

from aegis.security.prompts import PromptId


class InferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: PromptId
    approved: Literal[True]


class InferenceResponse(BaseModel):
    status: Literal["completed"] = "completed"
    provider: Literal["gemini"] = "gemini"
    model: str
    message: str
    transmitted: Literal[True] = True
    executed: Literal[False] = False
