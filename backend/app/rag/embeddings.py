import hashlib
import math
import re
from typing import Iterable, List


LATIN_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]+", re.UNICODE)
CJK_SEQUENCE_PATTERN = re.compile(r"[\u4e00-\u9fff]+", re.UNICODE)


def tokenize(text: str) -> List[str]:
    lowered = text.lower()
    tokens = LATIN_TOKEN_PATTERN.findall(lowered)
    for sequence in CJK_SEQUENCE_PATTERN.findall(lowered):
        if len(sequence) == 1:
            continue
        tokens.extend(sequence[index : index + 2] for index in range(len(sequence) - 1))
        if len(sequence) >= 3:
            tokens.extend(sequence[index : index + 3] for index in range(len(sequence) - 2))
    if tokens:
        return tokens
    return [char for char in lowered if not char.isspace()]


class HashEmbeddingFunction:
    """Deterministic local embeddings so RAG works without external API keys."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def __call__(self, input: Iterable[str]) -> List[List[float]]:
        return self.embed_documents(list(input))

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]
