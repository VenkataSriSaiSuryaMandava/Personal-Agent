from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, StringConstraints


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=4000
        )
    ]


class ChatResponse(BaseModel):
    status: Literal["preview"] = "preview"
    message: str
    transmitted: Literal[False] = False
    executed: Literal[False] = False
