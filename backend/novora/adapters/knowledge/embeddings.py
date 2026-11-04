"""Provider-neutral embedding infrastructure with remote inference and deterministic fallback."""
from __future__ import annotations

import hashlib
import logging
import math
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DIMENSION = 384


class EmbeddingService:
    """Generates embeddings using remote Hugging Face Inference API or deterministic fallback."""

    def __init__(self, api_token: Optional[str] = None) -> None:
        self.api_token = api_token or os.getenv("HUGGING_FACE_API_KEY") or os.getenv("HF_TOKEN")

    def is_remote_configured(self) -> bool:
        return bool(self.api_token and self.api_token.strip())

    def embed_query(self, text: str, model: str = DEFAULT_EMBEDDING_MODEL) -> List[float]:
        """Generate embedding vector for a single query."""
        results = self.embed_documents([text], model=model)
        return results[0] if results else [0.0] * DEFAULT_DIMENSION

    def embed_documents(
        self,
        texts: List[str],
        model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> List[List[float]]:
        """Generate embedding vectors for a list of document strings."""
        if not texts:
            return []

        if self.is_remote_configured():
            try:
                return self._remote_embed(texts, model)
            except Exception as exc:
                logger.warning("Remote HuggingFace embedding failed (%s); using deterministic fallback", exc)

        return [self._deterministic_vector(t, dimension=DEFAULT_DIMENSION) for t in texts]

    def _remote_embed(self, texts: List[str], model: str) -> List[List[float]]:
        """Call Hugging Face remote feature extraction endpoint."""
        from huggingface_hub import InferenceClient
        client = InferenceClient(token=self.api_token)
        # feature_extraction returns embeddings
        raw_result = client.feature_extraction(texts, model=model)
        # Result can be a numpy array or nested list
        if hasattr(raw_result, "tolist"):
            return raw_result.tolist()
        if isinstance(raw_result, list):
            return raw_result
        raise ValueError(f"Unexpected remote embedding return type: {type(raw_result)}")

    @staticmethod
    def _deterministic_vector(text: str, dimension: int = DEFAULT_DIMENSION) -> List[float]:
        """Generate a deterministic normalized unit vector from text content using cryptographic hashing."""
        seed_bytes = text.strip().lower().encode("utf-8")
        vec: List[float] = []

        # Generate pseudo-random deterministic floats from successive SHA-256 hashes
        counter = 0
        while len(vec) < dimension:
            h = hashlib.sha256(seed_bytes + counter.to_bytes(4, "big")).digest()
            for i in range(0, len(h), 4):
                if len(vec) >= dimension:
                    break
                int_val = int.from_bytes(h[i : i + 4], "big", signed=True)
                vec.append(float(int_val) / 2147483648.0)
            counter += 1

        # Normalize to unit length
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [round(x / norm, 6) for x in vec]

    @staticmethod
    def validate_compatibility(model_a: str, model_b: str) -> bool:
        """Verify that two embedding model identifiers are compatible for query-index alignment."""
        if not model_a or not model_b:
            return False
        clean_a = model_a.strip().lower()
        clean_b = model_b.strip().lower()
        if clean_a == clean_b:
            return True
        # Match base names ignoring repo prefixes
        return clean_a.split("/")[-1] == clean_b.split("/")[-1]

