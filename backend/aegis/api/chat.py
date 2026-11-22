from fastapi import APIRouter, Depends
from aegis.api.auth import require_owner

from aegis.schemas.chat import ChatRequest, ChatResponse
from aegis.services.assistant import preview_request

router = APIRouter(prefix="/api/v1")


@router.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(require_owner)],
)
def chat(request: ChatRequest) -> ChatResponse:
    return preview_request(request)
