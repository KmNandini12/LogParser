"""Dense Vector Embedding Generator using all-MiniLM-L6-v2."""

import logging
from typing import List, Optional
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generates 384-dimensional dense semantic vectors using local all-MiniLM-L6-v2."""

    _instance: Optional["EmbeddingGenerator"] = None
    _model: Optional[SentenceTransformer] = None

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize local embedding transformer model."""
        self.model_name = model_name
        if EmbeddingGenerator._model is None:
            logger.info(f"Loading local SentenceTransformer model: {model_name}...")
            EmbeddingGenerator._model = SentenceTransformer(model_name)
        self.model = EmbeddingGenerator._model

    def embed_text(self, text: str) -> List[float]:
        """Convert a single string into a 384-dimensional normalized vector.

        Args:
            text: Input string.

        Returns:
            List of 384 floating-point numbers.
        """
        clean_text = text.strip()
        if not clean_text:
            return [0.0] * 384
        embedding = self.model.encode(clean_text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Encode multiple texts in batches for efficiency.

        Args:
            texts: List of strings.
            batch_size: Batch size for inference.

        Returns:
            List of 384-dimensional float vectors.
        """
        if not texts:
            return []
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()
