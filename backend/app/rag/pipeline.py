import uuid
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set

from app.core.config import get_settings
from app.models.config import LLMConfig
from app.rag.chunker import AdaptiveChunker
from app.rag.entities import EntityExtractor
from app.rag.reranker import Reranker
from app.rag.router import QueryAnalyzer
from app.rag.schemas import IndexedChunk, IngestResult, RetrieveResult
from app.rag.storage import HybridStorage


class RAGPipeline:
    def __init__(self) -> None:
        settings = get_settings()
        self.chunker = AdaptiveChunker()
        self.entity_extractor = EntityExtractor()
        self.storage = HybridStorage(settings.rag_chroma_path, settings.rag_bm25_path)
        self.query_analyzer = QueryAnalyzer()
        self.reranker = Reranker()

    def ingest_text(
        self,
        text: str,
        filename: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IngestResult:
        metadata = metadata or {}
        document_id = str(metadata.get("document_id") or uuid.uuid4())
        base_metadata = {**metadata, "document_id": document_id, "filename": filename}
        strategy, documents = self.chunker.split_text(text, base_metadata)

        chunks: List[IndexedChunk] = []
        all_entities: Set[str] = set()
        for index, document in enumerate(documents):
            chunk_id = f"{document_id}:{index}"
            entities = self.entity_extractor.extract(document.page_content)
            all_entities.update(entities)
            chunks.append(
                IndexedChunk(
                    id=chunk_id,
                    text=document.page_content,
                    metadata={**document.metadata, "chunk_index": index},
                    entities=entities,
                )
            )

        self.storage.upsert_chunks(chunks)
        return IngestResult(
            document_id=document_id,
            filename=filename,
            strategy=strategy,
            chunk_count=len(chunks),
            entity_count=len(all_entities),
        )

    def retrieve_context(
        self,
        query: str,
        llm_config: Optional[LLMConfig] = None,
        top_k: int = 5,
    ) -> RetrieveResult:
        analysis = self.query_analyzer.analyze(query, llm_config)
        candidates = []
        if "vector" in analysis.routes:
            candidates.extend(self.storage.vector_search(query, top_k=max(8, top_k)))
        if "keyword" in analysis.routes:
            candidates.extend(self.storage.keyword_search(query, top_k=max(8, top_k)))
        if "graph" in analysis.routes:
            candidates.extend(self.storage.graph_search(query, top_k=max(8, top_k)))

        contexts = self.reranker.rerank(query, candidates, top_k=top_k)
        context_block = self._format_context_block(contexts)
        return RetrieveResult(query=query, analysis=analysis, contexts=contexts, context_block=context_block)

    def stats(self) -> Dict[str, Any]:
        return self.storage.stats()

    @staticmethod
    def _format_context_block(contexts) -> str:
        if not contexts:
            return ""
        lines = ["以下是 WanderBot 知识库召回的参考资料，请优先基于这些资料回答，并在不确定时说明："]
        for index, context in enumerate(contexts, start=1):
            filename = context.metadata.get("filename", "unknown")
            text = context.text.strip()
            if len(text) > 700:
                text = f"{text[:700]}..."
            lines.append(
                f"[{index}] source={context.source} score={context.score:.3f} file={filename}\n{text}"
            )
        return "\n\n".join(lines)


@lru_cache
def get_rag_pipeline() -> RAGPipeline:
    return RAGPipeline()
