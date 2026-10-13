from typing import Any, Dict, List, Optional, Protocol
from pydantic import BaseModel, Field

class VectorDocument(BaseModel):
    id: str
    text: str
    score: float = 0.0
    tenant_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class VectorSearchRequest(BaseModel):
    tenant_id: str = Field(min_length=1, description="Tenant ID to enforce multi-tenant isolation")
    query_text: Optional[str] = None
    query_vector: Optional[List[float]] = None
    top_k: int = Field(default=5, ge=1, le=50, description="Capped at maximum 50 results per query")
    filter_metadata: Dict[str, Any] = Field(default_factory=dict)

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

class VectorStoreConnector(Protocol):
    """Protocol for customer-owned vector search infrastructure."""

    def search(self, request: VectorSearchRequest) -> List[VectorDocument]:
        ...

class GraphStoreConnector(Protocol):
    """Protocol for customer-owned graph store infrastructure."""

    def query_subgraph(
        self,
        entity_id: str,
        tenant_id: str,
        relationship_type: Optional[str] = None,
        max_depth: int = 1,
    ) -> GraphQueryResult:
        ...
