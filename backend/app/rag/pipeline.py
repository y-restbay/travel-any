import uuid
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.config import LLMConfig
from app.rag.chunker import AdaptiveChunker
from app.rag.entities import EntityExtractor
from app.rag.reranker import Reranker
from app.rag.router import QueryAnalyzer
from app.rag.schemas import IndexedChunk, IngestResult, QueryAnalysis, RAGDebugResult, RAGTraceStep, RetrievalCandidate, RetrieveResult
from app.rag.storage import HybridStorage
from app.services.config_service import ensure_defaults, get_active_embedding_config


class RAGPipeline:
    def __init__(self) -> None:
        settings = get_settings()
        with SessionLocal() as db:
            ensure_defaults(db)
            embedding_config = get_active_embedding_config(db)
        self.chunker = AdaptiveChunker()
        self.entity_extractor = EntityExtractor()
        self.storage = HybridStorage(settings.rag_chroma_path, settings.rag_bm25_path, settings, embedding_config)
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
        route_candidates = self._retrieve_by_routes(query, analysis, top_k=top_k)
        candidates = [candidate for candidates in route_candidates.values() for candidate in candidates]
        contexts = self.reranker.rerank(query, candidates, top_k=top_k, route_weights=analysis.route_weights)
        context_block = self._format_context_block(contexts)
        return RetrieveResult(query=query, analysis=analysis, contexts=contexts, context_block=context_block)

    def debug_retrieve(
        self,
        query: str,
        llm_config: Optional[LLMConfig] = None,
        top_k: int = 5,
    ) -> RAGDebugResult:
        trace: List[RAGTraceStep] = [
            RAGTraceStep(
                step="step_1",
                title="存储与切片基建",
                status="ready",
                detail="ChromaDB、BM25 和轻量实体索引已初始化；上传文档时会先按 metadata 自适应切片再写入三类索引。",
                data=self.storage.stats(),
            )
        ]

        analysis = self.query_analyzer.analyze(query, llm_config)
        trace.append(
            RAGTraceStep(
                step="step_2",
                title="查询路由",
                status="done",
                detail=analysis.reasoning,
                data={
                    "routes": analysis.routes,
                    "route_weights": analysis.route_weights,
                    "decision_source": analysis.decision_source,
                },
            )
        )

        route_candidates = self._retrieve_by_routes(query, analysis, top_k=top_k)

        merged_candidates = []
        for candidates in route_candidates.values():
            merged_candidates.extend(candidates)

        trace.append(
            RAGTraceStep(
                step="step_3",
                title="多路召回",
                status="done",
                detail="按路由并行调用检索器，并返回各路候选片段。",
                data={
                    "candidate_count": len(merged_candidates),
                    "route_weights": analysis.route_weights,
                    "decision_source": analysis.decision_source,
                    "routes": {
                        route: [self._candidate_summary(item).model_dump() for item in candidates]
                        for route, candidates in route_candidates.items()
                    },
                },
            )
        )

        contexts = self.reranker.rerank(query, merged_candidates, top_k=top_k, route_weights=analysis.route_weights)
        context_block = self._format_context_block(contexts)
        result = RetrieveResult(query=query, analysis=analysis, contexts=contexts, context_block=context_block)
        trace.append(
            RAGTraceStep(
                step="step_4",
                title="合并与重排",
                status="done",
                detail="候选片段按 chunk_id 去重后由本地 reranker 二次打分，最终选出 Top-K 注入回答上下文。",
                data={
                    "route_weights": analysis.route_weights,
                    "decision_source": analysis.decision_source,
                    "reranked_count": len(contexts),
                    "top_contexts": [self._candidate_summary(item).model_dump() for item in contexts],
                    "context_injected": bool(context_block),
                },
            )
        )
        return RAGDebugResult(query=query, trace=trace, retrieve_result=result)

    def stats(self) -> Dict[str, Any]:
        return self.storage.stats()

    def rebuild_vector_index(self) -> Dict[str, Any]:
        indexed_count = self.storage.rebuild_vector_index()
        return {**self.storage.stats(), "reindexed_chunks": indexed_count}

    def _retrieve_by_routes(self, query: str, analysis: QueryAnalysis, top_k: int = 5) -> Dict[str, List]:
        route_candidates: Dict[str, List] = {}
        base_k = max(8, top_k)
        for route in analysis.routes:
            weight = analysis.route_weights.get(route, 0.0)
            route_k = max(top_k, int(round(base_k * (0.75 + weight))))
            if route == "vector":
                route_candidates["vector"] = self.storage.vector_search(query, top_k=route_k)
            elif route == "keyword":
                route_candidates["keyword"] = self.storage.keyword_search(query, top_k=route_k)
            elif route == "graph":
                route_candidates["graph"] = self.storage.graph_search(query, top_k=route_k)
        return route_candidates

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

    @staticmethod
    def _candidate_summary(context) -> RetrievalCandidate:
        text = context.text.strip()
        return RetrievalCandidate(
            chunk_id=context.chunk_id,
            source=context.source,
            score=context.score,
            filename=context.metadata.get("filename"),
            preview=f"{text[:180]}..." if len(text) > 180 else text,
        )


@lru_cache
def get_rag_pipeline() -> RAGPipeline:
    return RAGPipeline()
