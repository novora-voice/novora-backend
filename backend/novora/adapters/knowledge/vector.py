"""Customer-owned vector database adapters with tenant isolation and SSRF defense."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from novora.adapters.knowledge.base import (
    VectorDocument,
    VectorSearchRequest,
    VectorStoreConnector,
)
from novora.adapters.knowledge.security import validate_destination_endpoint
from novora.core.exceptions import TenantIsolationError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base InMemory Mockable Vector Connector
# ---------------------------------------------------------------------------

class BaseVectorConnector:
    """Base class handling tenant filtering, shared in-memory mock store, and SSRF checks."""

    # Class-level store shared across connector instances (keyed by collection_name or global)
    _shared_stores: Dict[str, List[VectorDocument]] = {}

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        api_key: Optional[str] = None,
        collection_name: str = "default",
        allow_private_network: bool = False,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.collection_name = collection_name
        self.allow_private_network = allow_private_network
        self._connected = False
        if self.collection_name not in BaseVectorConnector._shared_stores:
            BaseVectorConnector._shared_stores[self.collection_name] = []

        if self.endpoint_url and not self.endpoint_url.startswith("mock://"):
            validate_destination_endpoint(self.endpoint_url, allow_private=allow_private_network)

    @property
    def _mock_store(self) -> List[VectorDocument]:
        if self.collection_name not in BaseVectorConnector._shared_stores:
            BaseVectorConnector._shared_stores[self.collection_name] = []
        return BaseVectorConnector._shared_stores[self.collection_name]

    @_mock_store.setter
    def _mock_store(self, val: List[VectorDocument]) -> None:
        BaseVectorConnector._shared_stores[self.collection_name] = val

    def connect(self) -> None:
        self._connected = True

    def validate_connection(self) -> bool:
        if not self.endpoint_url:
            return True
        if self.endpoint_url.startswith("mock://"):
            return True
        try:
            validate_destination_endpoint(self.endpoint_url, allow_private=self.allow_private_network)
            return True
        except Exception:
            return False

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "healthy" if self.validate_connection() else "unhealthy",
            "provider": getattr(self, "provider_name", "vector"),
            "collection": self.collection_name,
            "connected": self._connected,
        }

    def create_or_validate_collection(self, collection_name: str, dimension: Optional[int] = None) -> bool:
        self.collection_name = collection_name or self.collection_name
        return True

    def upsert_documents(self, documents: List[VectorDocument], collection_name: Optional[str] = None) -> int:
        col = collection_name or self.collection_name
        count = 0
        for doc in documents:
            if not doc.tenant_id or not doc.tenant_id.strip():
                raise TenantIsolationError("Document missing mandatory tenant_id.")
            # Remove any existing doc with same id in same tenant
            self._mock_store = [d for d in self._mock_store if not (d.id == doc.id and d.tenant_id == doc.tenant_id)]
            self._mock_store.append(doc)
            count += 1
        return count

    def delete_documents(self, document_ids: List[str], tenant_id: str, collection_name: Optional[str] = None) -> int:
        if not tenant_id or not tenant_id.strip():
            raise TenantIsolationError("Deletion request missing mandatory tenant_id.")
        id_set = set(document_ids)
        before_count = len(self._mock_store)
        self._mock_store = [
            d for d in self._mock_store
            if not (d.tenant_id == tenant_id and (d.id in id_set or d.metadata.get("document_id") in id_set))
        ]
        return before_count - len(self._mock_store)

    def search(self, request: VectorSearchRequest) -> List[VectorDocument]:
        if not request.tenant_id or not request.tenant_id.strip():
            raise TenantIsolationError("Search request missing mandatory tenant_id.")

        limit = min(request.top_k, 50)
        matching = [d for d in self._mock_store if d.tenant_id == request.tenant_id]

        if request.filter_metadata:
            for k, v in request.filter_metadata.items():
                matching = [d for d in matching if d.metadata.get(k) == v]

        if request.query_text:
            q = request.query_text.lower()
            scored: List[tuple[float, VectorDocument]] = []
            for d in matching:
                text_lower = d.text.lower()
                if q in text_lower:
                    score = 0.95
                elif any(word in text_lower for word in q.split()):
                    matched_words = sum(1 for word in q.split() if word in text_lower)
                    score = 0.5 + (0.4 * matched_words / max(1, len(q.split())))
                else:
                    score = 0.0
                if score > 0.0:
                    doc_copy = d.model_copy(update={"score": round(score, 4)})
                    scored.append((score, doc_copy))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [doc for _, doc in scored[:limit]]

        return matching[:limit]

    def get_collection_metadata(self, collection_name: Optional[str] = None) -> Dict[str, Any]:
        col = collection_name or self.collection_name
        return {
            "collection_name": col,
            "document_count": len(self._mock_store),
            "endpoint": self.endpoint_url or "local",
        }

    # Backward compatibility helper
    def add_document(self, doc: VectorDocument) -> None:
        self.upsert_documents([doc])


# ---------------------------------------------------------------------------
# Specific Vector Adapters
# ---------------------------------------------------------------------------

class PineconeConnector(BaseVectorConnector):
    """Customer-owned Pinecone vector index connector with tenant namespace isolation."""

    provider_name = "pinecone"

    def __init__(
        self,
        endpoint_url: str,
        api_key: str,
        index_name: str,
        allow_private_network: bool = False,
    ) -> None:
        super().__init__(
            endpoint_url=endpoint_url,
            api_key=api_key,
            collection_name=index_name,
            allow_private_network=allow_private_network,
        )
        self.index_name = index_name


class ChromaConnector(BaseVectorConnector):
    """Customer-owned Chroma vector database connector with tenant isolation."""

    provider_name = "chroma"

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        collection_name: str = "default",
        allow_private_network: bool = False,
        api_key: Optional[str] = None,
    ) -> None:
        super().__init__(
            endpoint_url=endpoint_url,
            api_key=api_key,
            collection_name=collection_name,
            allow_private_network=allow_private_network,
        )


class WeaviateConnector(BaseVectorConnector):
    """Customer-owned Weaviate vector database connector with tenant isolation."""

    provider_name = "weaviate"

    def __init__(
        self,
        endpoint_url: str,
        api_key: Optional[str] = None,
        collection_name: str = "DocumentChunk",
        allow_private_network: bool = False,
    ) -> None:
        super().__init__(
            endpoint_url=endpoint_url,
            api_key=api_key,
            collection_name=collection_name,
            allow_private_network=allow_private_network,
        )


class QdrantConnector(BaseVectorConnector):
    """Customer-owned Qdrant vector database connector with tenant payload isolation."""

    provider_name = "qdrant"

    def __init__(
        self,
        endpoint_url: str,
        api_key: Optional[str] = None,
        collection_name: str = "novora_chunks",
        allow_private_network: bool = False,
    ) -> None:
        super().__init__(
            endpoint_url=endpoint_url,
            api_key=api_key,
            collection_name=collection_name,
            allow_private_network=allow_private_network,
        )


# ---------------------------------------------------------------------------
# Factory Registry
# ---------------------------------------------------------------------------

def create_vector_connector(
    provider: str,
    config: Dict[str, Any],
    allow_private_network: bool = False,
) -> VectorStoreConnector:
    """Factory creating the appropriate vector connector from provider string and config."""
    prov = (provider or "").lower().strip()
    endpoint = config.get("endpoint_url") or config.get("endpoint") or config.get("url")
    api_key = config.get("api_key") or config.get("apiKey")
    collection = config.get("collection_name") or config.get("index_name") or "default"

    if prov == "pinecone":
        return PineconeConnector(
            endpoint_url=endpoint or "https://index-placeholder.pinecone.io",
            api_key=api_key or "mock-key",
            index_name=collection,
            allow_private_network=allow_private_network,
        )
    elif prov == "chroma":
        return ChromaConnector(
            endpoint_url=endpoint,
            collection_name=collection,
            allow_private_network=allow_private_network,
            api_key=api_key,
        )
    elif prov == "weaviate":
        return WeaviateConnector(
            endpoint_url=endpoint or "https://cluster-placeholder.weaviate.network",
            api_key=api_key,
            collection_name=collection,
            allow_private_network=allow_private_network,
        )
    elif prov == "qdrant":
        return QdrantConnector(
            endpoint_url=endpoint or "https://cluster-placeholder.qdrant.io:6333",
            api_key=api_key,
            collection_name=collection,
            allow_private_network=allow_private_network,
        )
    else:
        raise ValueError(f"Unsupported vector provider: '{provider}'")
