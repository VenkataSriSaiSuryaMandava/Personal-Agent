from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    username: str = Field(
        min_length=1,
        max_length=128,
    )

    password: str = Field(
        min_length=1,
        max_length=128,
        repr=False,
    )


class LoginResponse(BaseModel):

    authenticated: Literal[True] = True
    session_token: str = Field(repr=False)
    expires_in: int


class SessionResponse(BaseModel):

    authenticated: Literal[True] = True


class LogoutResponse(BaseModel):

    authenticated: Literal[False] = False
