from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ChunkStrategy = Literal["long_form", "short_form"]
QueryRoute = Literal["vector", "keyword", "graph", "cloud"]
RouteDecisionSource = Literal["llm", "rules", "rules_fallback", "cloud"]


class IndexedChunk(BaseModel):
    id: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    entities: List[str] = Field(default_factory=list)


class IngestResult(BaseModel):
    document_id: str
    filename: str
    strategy: ChunkStrategy
    chunk_count: int
    entity_count: int


class QueryAnalysis(BaseModel):
    routes: List[QueryRoute]
    reasoning: str
    route_weights: Dict[QueryRoute, float] = Field(default_factory=dict)
    decision_source: RouteDecisionSource = "rules"


class RetrievedContext(BaseModel):
    chunk_id: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source: str
    score: float


class RetrieveResult(BaseModel):
    query: str
    analysis: QueryAnalysis
    contexts: List[RetrievedContext]
    context_block: str


class TextIngestRequest(BaseModel):
    text: str = Field(min_length=1)
    filename: str = "manual-note.txt"
    doc_type: Optional[str] = None
    source: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class RetrievalCandidate(BaseModel):
    chunk_id: str
    source: str
    score: float
    filename: Optional[str] = None
    preview: str


class RAGTraceStep(BaseModel):
    step: str
    title: str
    status: str
    detail: str
    data: Dict[str, Any] = Field(default_factory=dict)


class RAGDebugResult(BaseModel):
    query: str
    trace: List[RAGTraceStep]
    retrieve_result: RetrieveResult
