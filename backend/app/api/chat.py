from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.chat import ChatStreamRequest
from app.services.chat_service import chat_stream, chat_stream_with_tools
from app.services.config_service import get_active_llm_config, get_active_system_prompt
from app.services.llm_factory import uses_mock_provider
from app.services.tool_service import get_active_tools

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream")
async def stream_chat(payload: ChatStreamRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    llm_config = get_active_llm_config(db)
    system_prompt = get_active_system_prompt(db)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    active_tools = get_active_tools(db)

    if active_tools and not uses_mock_provider(llm_config):
        stream = chat_stream_with_tools(payload.messages, llm_config, system_prompt, active_tools)
    else:
        stream = chat_stream(payload.messages, llm_config, system_prompt)

    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers=headers,
    )
