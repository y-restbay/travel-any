from typing import List, Literal, Optional

from pydantic import BaseModel, Field


ChatRole = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    role: ChatRole
    content: str = Field(min_length=1)


class ChatStreamRequest(BaseModel):
    messages: List[ChatMessage] = Field(default_factory=list)
    conversation_id: Optional[str] = None
