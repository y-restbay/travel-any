from typing import List, Literal, Optional

from pydantic import BaseModel, Field


ChatRole = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    role: ChatRole
    content: str = Field(min_length=1)
    # 当用户在该条消息里上传了图片时，由 /api/upload/image 返回的引用 ID。
    # 模型调度 identify_landmark 工具时把它当作参数传回后端，由后端去取图。
    image_ref: Optional[str] = None
    # 多图：一次上传多张图片的引用 ID 列表。前端并发上传多张后，
    # 将全部 ref 放到此字段中，后端组装标记让 LLM 逐一识别。
    image_refs: Optional[list[str]] = None


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
