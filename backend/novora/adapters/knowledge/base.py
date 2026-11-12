"""Provider-neutral interfaces and models for customer-owned knowledge infrastructure."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from pydantic import BaseModel, Field


class VectorDocument(BaseModel):
    id: str
    text: str
    score: float = 0.0
    tenant_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None


class VectorSearchRequest(BaseModel):
    tenant_id: str = Field(min_length=1, description="Tenant/Org ID to enforce multi-tenant isolation")
    query_text: Optional[str] = None
    query_vector: Optional[List[float]] = None
    top_k: int = Field(default=5, ge=1, le=50, description="Capped at maximum 50 results per query")
    filter_metadata: Dict[str, Any] = Field(default_factory=dict)
    namespace: Optional[str] = None


class GraphNode(BaseModel):
    id: str
    labels: List[str] = Field(default_factory=list)
    properties: Dict[str, Any] = Field(default_factory=dict)


class GraphRelationship(BaseModel):
    id: str
    type: str
    start_node_id: str
    end_node_id: str
    properties: Dict[str, Any] = Field(default_factory=dict)


class GraphQueryResult(BaseModel):
    tenant_id: str
    nodes: List[GraphNode] = Field(default_factory=list)
    relationships: List[GraphRelationship] = Field(default_factory=list)


@runtime_checkable
class VectorStoreConnector(Protocol):
    """Protocol for customer-owned vector search infrastructure."""

    def connect(self) -> None:
        ...

    def validate_connection(self) -> bool:
        ...

    def health_check(self) -> Dict[str, Any]:
        ...

    def create_or_validate_collection(self, collection_name: str, dimension: Optional[int] = None) -> bool:
        ...

    def upsert_documents(self, documents: List[VectorDocument], collection_name: Optional[str] = None) -> int:
        ...

    def delete_documents(self, document_ids: List[str], tenant_id: str, collection_name: Optional[str] = None) -> int:
        ...

    def search(self, request: VectorSearchRequest) -> List[VectorDocument]:
        ...

    def get_collection_metadata(self, collection_name: Optional[str] = None) -> Dict[str, Any]:
        ...


@runtime_checkable
class GraphStoreConnector(Protocol):
    """Protocol for customer-owned graph store infrastructure."""

    def connect(self) -> None:
        ...

    def validate_connection(self) -> bool:
        ...

    def health_check(self) -> Dict[str, Any]:
        ...

    def create_or_validate_schema(self) -> bool:
        ...

    def query(self, query: str, parameters: Optional[Dict[str, Any]] = None, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        ...

    def query_subgraph(
        self,
        entity_id: str,
        tenant_id: str,
        relationship_type: Optional[str] = None,
        max_depth: int = 1,
    ) -> GraphQueryResult:
        ...

    def retrieve_related_entities(
        self,
        entity_ids: List[str],
        tenant_id: str,
        max_depth: int = 1,
    ) -> GraphQueryResult:
        ...
