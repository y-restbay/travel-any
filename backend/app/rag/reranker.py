from collections import defaultdict
from typing import Dict, List

from app.rag.embeddings import tokenize
from app.rag.schemas import RetrievedContext


class Reranker:
    """Local reranker placeholder; can be swapped for BGE or Cohere Rerank later."""

    def rerank(self, query: str, contexts: List[RetrievedContext], top_k: int = 5, min_score: float = 0.26) -> List[RetrievedContext]:
        query_terms = set(tokenize(query))
        merged: Dict[str, RetrievedContext] = {}
        source_bonus = defaultdict(float, {"vector": 0.04, "keyword": 0.06, "graph": 0.08})

        for context in contexts:
            existing = merged.get(context.chunk_id)
            if existing is None or context.score > existing.score:
                merged[context.chunk_id] = context
            elif existing is not None:
                existing.score = max(existing.score, context.score)
                existing.source = f"{existing.source}+{context.source}"

        scored: List[RetrievedContext] = []
        for context in merged.values():
            doc_terms = set(tokenize(context.text))
            lexical = len(query_terms.intersection(doc_terms)) / max(1, len(query_terms))
            context.score = round((context.score * 0.7) + (lexical * 0.25) + source_bonus[context.source.split("+")[0]], 4)
            if context.score >= min_score:
                scored.append(context)

        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]
