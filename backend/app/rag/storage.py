import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

import chromadb
from chromadb.config import Settings
from rank_bm25 import BM25Okapi

from app.rag.embeddings import create_embedding_function, tokenize
from app.rag.schemas import IndexedChunk, RetrievedContext


class HybridStorage:
    def __init__(self, chroma_path: str, bm25_path: str, settings, embedding_config=None) -> None:
        self.chroma_path = Path(chroma_path)
        self.bm25_path = Path(bm25_path)
        self.chroma_path.mkdir(parents=True, exist_ok=True)
        self.bm25_path.parent.mkdir(parents=True, exist_ok=True)

        self.embedding_function = create_embedding_function(settings, embedding_config)
        self.embedding_profile = self.embedding_function.profile
        self.client = chromadb.PersistentClient(
            path=str(self.chroma_path),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=self.embedding_profile.collection_name,
            metadata={
                "hnsw:space": "cosine",
                "embedding_provider": self.embedding_profile.provider,
                "embedding_model": self.embedding_profile.model,
            },
        )
        self.chunks: List[IndexedChunk] = []
        self.entity_index: Dict[str, List[str]] = {}
        self.bm25: Optional[BM25Okapi] = None
        self._load_bm25()

    def upsert_chunks(self, chunks: List[IndexedChunk]) -> None:
        if not chunks:
            return

        ids = [chunk.id for chunk in chunks]
        texts = [chunk.text for chunk in chunks]
        embeddings = self.embedding_function.embed_documents(texts)
        metadatas = [self._safe_metadata({**chunk.metadata, "entities": ", ".join(chunk.entities)}) for chunk in chunks]

        self.collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
        self._merge_chunks(chunks)
        self._persist_bm25()
        self._rebuild_bm25()

    def rebuild_vector_index(self) -> int:
        if not self.chunks:
            return 0
        ids = [chunk.id for chunk in self.chunks]
        texts = [chunk.text for chunk in self.chunks]
        embeddings = self.embedding_function.embed_documents(texts)
        metadatas = [self._safe_metadata({**chunk.metadata, "entities": ", ".join(chunk.entities)}) for chunk in self.chunks]
        self.collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
        return len(self.chunks)

    def vector_search(self, query: str, top_k: int = 8) -> List[RetrievedContext]:
        if self.collection.count() == 0:
            return []

        result = self.collection.query(
            query_embeddings=[self.embedding_function.embed_query(query)],
            n_results=min(top_k, self.collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        contexts: List[RetrievedContext] = []
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            score = max(0.0, 1.0 - float(distance or 0.0))
            if score < 0.18:
                continue
            contexts.append(
                RetrievedContext(
                    chunk_id=chunk_id,
                    text=document,
                    metadata=metadata or {},
                    source="vector",
                    score=score,
                )
            )
        return contexts

    def keyword_search(self, query: str, top_k: int = 8) -> List[RetrievedContext]:
        if not self.chunks or self.bm25 is None:
            return []

        query_tokens = set(tokenize(query))
        if not query_tokens:
            return []

        scores = self.bm25.get_scores(list(query_tokens))
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)[:top_k]
        max_score = max([score for _, score in ranked], default=0.0) or 1.0
        contexts: List[RetrievedContext] = []
        for index, raw_score in ranked:
            if raw_score <= 0:
                continue
            chunk = self.chunks[index]
            doc_tokens = set(tokenize(chunk.text))
            overlap = query_tokens.intersection(doc_tokens)
            if not overlap:
                continue
            normalized_score = float(raw_score / max_score)
            if normalized_score < 0.18:
                continue
            contexts.append(
                RetrievedContext(
                    chunk_id=chunk.id,
                    text=chunk.text,
                    metadata=chunk.metadata,
                    source="keyword",
                    score=normalized_score,
                )
            )
        return contexts

    def graph_search(self, query: str, top_k: int = 8) -> List[RetrievedContext]:
        matched_ids: set = set()
        for entity, chunk_ids in self.entity_index.items():
            if entity in query:
                matched_ids.update(chunk_ids)

        id_to_chunk = {chunk.id: chunk for chunk in self.chunks}
        contexts: List[RetrievedContext] = []
        for chunk_id in list(matched_ids)[:top_k]:
            chunk = id_to_chunk.get(chunk_id)
            if chunk is None:
                continue
            contexts.append(
                RetrievedContext(
                    chunk_id=chunk.id,
                    text=chunk.text,
                    metadata=chunk.metadata,
                    source="graph",
                    score=0.8,
                )
            )
        return contexts

    def stats(self) -> Dict[str, Any]:
        documents: Dict[str, Dict[str, Any]] = {}
        for chunk in self.chunks:
            document_id = str(chunk.metadata.get("document_id") or "unknown")
            summary = documents.setdefault(
                document_id,
                {
                    "document_id": document_id,
                    "filename": chunk.metadata.get("filename", "unknown"),
                    "chunk_count": 0,
                    "strategy": chunk.metadata.get("chunk_strategy"),
                    "source": chunk.metadata.get("source"),
                    "doc_type": chunk.metadata.get("doc_type"),
                },
            )
            summary["chunk_count"] += 1

        return {
            "chunk_count": len(self.chunks),
            "vector_count": self.collection.count(),
            "entity_count": len(self.entity_index),
            "chroma_path": str(self.chroma_path),
            "collection_name": self.embedding_profile.collection_name,
            "embedding_provider": self.embedding_profile.provider,
            "embedding_model": self.embedding_profile.model,
            "is_real_embedding": self.embedding_profile.is_real_embedding,
            "bm25_path": str(self.bm25_path),
            "documents": sorted(documents.values(), key=lambda item: str(item.get("filename", ""))),
        }

    def _merge_chunks(self, chunks: Iterable[IndexedChunk]) -> None:
        by_id = {chunk.id: chunk for chunk in self.chunks}
        for chunk in chunks:
            by_id[chunk.id] = chunk
        self.chunks = list(by_id.values())
        self.entity_index = {}
        for chunk in self.chunks:
            for entity in chunk.entities:
                self.entity_index.setdefault(entity, []).append(chunk.id)

    def _rebuild_bm25(self) -> None:
        if not self.chunks:
            self.bm25 = None
            return
        self.bm25 = BM25Okapi([tokenize(chunk.text) for chunk in self.chunks])

    def _load_bm25(self) -> None:
        if not self.bm25_path.exists():
            self._rebuild_bm25()
            return
        payload = json.loads(self.bm25_path.read_text(encoding="utf-8"))
        self.chunks = [IndexedChunk.model_validate(item) for item in payload.get("chunks", [])]
        self.entity_index = {
            entity: list(chunk_ids) for entity, chunk_ids in payload.get("entity_index", {}).items()
        }
        self._rebuild_bm25()

    def _persist_bm25(self) -> None:
        payload = {
            "chunks": [chunk.model_dump() for chunk in self.chunks],
            "entity_index": self.entity_index,
        }
        self.bm25_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _safe_metadata(metadata: Dict[str, Any]) -> Dict[str, Union[str, int, float, bool]]:
        safe: Dict[str, Union[str, int, float, bool]] = {}
        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                safe[key] = value
            else:
                safe[key] = json.dumps(value, ensure_ascii=False)
        return safe
