from typing import Any, Dict, List, Tuple

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.rag.schemas import ChunkStrategy


class AdaptiveChunker:
    def choose_strategy(self, metadata: Dict[str, Any]) -> ChunkStrategy:
        doc_type = str(metadata.get("doc_type") or metadata.get("type") or "").lower()
        if doc_type in {"social", "post", "review", "short_review", "comment", "ugc"}:
            return "short_form"
        if doc_type in {"paper", "professional", "long", "guide", "report", "manual"}:
            return "long_form"

        text_length = int(metadata.get("text_length") or 0)
        return "short_form" if text_length < 1800 else "long_form"

    def split_text(self, text: str, metadata: Dict[str, Any]) -> Tuple[ChunkStrategy, List[Document]]:
        enriched_metadata = {**metadata, "text_length": len(text)}
        strategy = self.choose_strategy(enriched_metadata)

        if strategy == "long_form":
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                add_start_index=True,
            )
        else:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=300,
                chunk_overlap=50,
                add_start_index=True,
            )

        documents = splitter.create_documents([text], metadatas=[{**metadata, "chunk_strategy": strategy}])
        return strategy, documents
