from typing import List, Literal, Optional

from pydantic import BaseModel, Field


ChatRole = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    role: ChatRole
    content: str = Field(min_length=1)


ChatMode = Literal["single", "deep_thinking"]
KnowledgeSource = Literal["local", "cloud"]


class ChatStreamRequest(BaseModel):
    messages: List[ChatMessage] = Field(default_factory=list)
    conversation_id: Optional[str] = None
    mode: ChatMode = "single"
    # local=本地自建 RAG（默认）；cloud=阿里云百炼云知识库（纯检索，云端已重排）
    knowledge_source: KnowledgeSource = "local"
    # True=每轮强制 Tavily 联网检索，把网页结果编号注入 prompt（与 cloud 互斥）
    web_search: bool = False


class ChatResumeRequest(BaseModel):
    """用户对 interrupt 给出回复后 resume 之前的 supervisor graph。"""

    conversation_id: str
    decision: object = True  # True/False / 'approve' / {'action': 'approve', ...}
