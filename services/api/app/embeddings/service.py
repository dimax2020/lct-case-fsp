"""intfloat/multilingual-e5-base embeddings.

Prefixes are `query:` and `passage:`. The model is loaded once per process.
Without the optional .[ml] extra, embed() returns 768-d zero vectors so the API
process still runs. The worker image needs INSTALL_ML=1 for real vectors.
"""

import asyncio
import logging
from typing import Any

from app.core.db import EMBEDDING_DIM
from app.core.errors import AppError
from app.core.settings import get_settings

logger = logging.getLogger(__name__)

_model: Any = None
_missing = False
_BATCH = 32


def peek_model() -> Any:
    """Return the loaded model, or None if it has not been loaded yet."""
    return _model


def reset_model() -> None:
    global _model, _missing
    _model = None
    _missing = False


def _import_sentence_transformer() -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer


def load_model() -> Any:
    global _model, _missing
    if _model is not None:
        return _model
    if _missing:
        return None
    try:
        factory = _import_sentence_transformer()
    except ImportError:
        _missing = True
        logger.warning(
            "sentence-transformers is not installed; embed() returns zero vectors. Build with INSTALL_ML=1."
        )
        return None
    _model = factory(get_settings().embedding_model)
    return _model


async def embed(texts: list[str], *, prefix: str = "passage") -> list[list[float]]:
    if not texts:
        return []
    kind = prefix if prefix in {"query", "passage"} else "passage"
    labeled = [f"{kind}: {text}" for text in texts]
    model = load_model()
    if model is None:
        return [[0.0] * EMBEDDING_DIM for _ in texts]
    vectors = await asyncio.to_thread(model.encode, labeled, batch_size=_BATCH, normalize_embeddings=True)
    rows: list[list[float]] = []
    for row in vectors:
        values = [float(item) for item in row]
        if len(values) != EMBEDDING_DIM:
            raise AppError(
                "embedding_dim",
                f"Модель эмбеддингов вернула размер {len(values)}, ожидается {EMBEDDING_DIM}",
                status_code=500,
            )
        rows.append(values)
    return rows
