from aegis.schemas.chat import ChatRequest, ChatResponse


def preview_request(request: ChatRequest) -> ChatResponse:
    # Input is validated but deliberately not stored,
    # echoed or forwarded.
    return ChatResponse(
        message="AI provider is not configured. No action was executed."
    )
