"""e5 embeddings.

The real model is intfloat/multilingual-e5-base (sentence-transformers, prefixes
query:/passage:, loaded once per worker). Install the optional extra: .[ml].
This stub returns a zero vector so neighbours can run without the model.
"""

from app.core.db import EMBEDDING_DIM


async def embed(texts: list[str]) -> list[list[float]]:
    return [[0.0] * EMBEDDING_DIM for _ in texts]
