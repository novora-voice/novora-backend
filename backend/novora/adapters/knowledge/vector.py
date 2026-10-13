from typing import Any, Dict, List, Optional
from novora.adapters.knowledge.base import (
    VectorDocument,
    VectorSearchRequest,
    VectorStoreConnector,
)
from novora.adapters.knowledge.security import validate_destination_endpoint
from novora.core.exceptions import TenantIsolationError

class PineconeConnector(VectorStoreConnector):
    """Customer-owned Pinecone vector index connector with tenant namespace isolation and SSRF defense."""

    def __init__(
        self,
        endpoint_url: str,
        api_key: str,
        index_name: str,
        allow_private_network: bool = False,
    ) -> None:
        validate_destination_endpoint(endpoint_url, allow_private=allow_private_network)
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.index_name = index_name
        self._mock_store: List[VectorDocument] = []

    def add_document(self, doc: VectorDocument) -> None:
        """Helper to seed mock data in testing."""
        self._mock_store.append(doc)

    def search(self, request: VectorSearchRequest) -> List[VectorDocument]:
        """Executes read-only vector search strictly scoped to tenant_id namespace."""
        if not request.tenant_id or not request.tenant_id.strip():
            raise TenantIsolationError("Search request missing mandatory tenant_id.")

        # Hard limit results
        limit = min(request.top_k, 50)

        # Tenant isolation guarantee: filter strictly by tenant_id
        matching = [
            doc for doc in self._mock_store
            if doc.tenant_id == request.tenant_id
        ]

        if request.query_text:
            query_lower = request.query_text.lower()
            matching = [
                d for d in matching
                if query_lower in d.text.lower() or any(query_lower in str(v).lower() for v in d.metadata.values())
            ]

        return matching[:limit]

class ChromaConnector(VectorStoreConnector):
    """Chroma vector database connector with tenant isolation."""

    def __init__(
        self,
        endpoint_url: str,
        collection_name: str,
        allow_private_network: bool = False,
    ) -> None:
        validate_destination_endpoint(endpoint_url, allow_private=allow_private_network)
        self.endpoint_url = endpoint_url
        self.collection_name = collection_name
        self._mock_store: List[VectorDocument] = []

    def add_document(self, doc: VectorDocument) -> None:
        self._mock_store.append(doc)

    def search(self, request: VectorSearchRequest) -> List[VectorDocument]:
        if not request.tenant_id:
            raise TenantIsolationError("Tenant ID required for Chroma search.")

        limit = min(request.top_k, 50)
        matching = [d for d in self._mock_store if d.tenant_id == request.tenant_id]

        if request.query_text:
            q = request.query_text.lower()
            matching = [d for d in matching if q in d.text.lower()]

        return matching[:limit]
