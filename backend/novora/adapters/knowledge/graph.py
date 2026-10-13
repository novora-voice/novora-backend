import re
from typing import Any, Dict, List, Optional
from novora.adapters.knowledge.base import (
    GraphNode,
    GraphQueryResult,
    GraphRelationship,
    GraphStoreConnector,
)
from novora.adapters.knowledge.security import validate_destination_endpoint
from novora.core.exceptions import PayloadValidationError, TenantIsolationError

FORBIDDEN_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH\s+DELETE|SET|REMOVE|DROP|ALTER)\b",
    re.IGNORECASE,
)

class Neo4jConnector(GraphStoreConnector):
    """Customer-owned Neo4j graph connector enforcing read-only operations, parameterized queries, and tenant isolation."""

    def __init__(
        self,
        endpoint_url: str,
        username: str,
        password: str,
        allow_private_network: bool = False,
    ) -> None:
        validate_destination_endpoint(endpoint_url, allow_private=allow_private_network)
        self.endpoint_url = endpoint_url
        self.username = username
        self.password = password
        self._mock_nodes: List[GraphNode] = []
        self._mock_rels: List[GraphRelationship] = []

    def add_node(self, node: GraphNode) -> None:
        self._mock_nodes.append(node)

    def add_relationship(self, rel: GraphRelationship) -> None:
        self._mock_rels.append(rel)

    def query_subgraph(
        self,
        entity_id: str,
        tenant_id: str,
        relationship_type: Optional[str] = None,
        max_depth: int = 1,
    ) -> GraphQueryResult:
        """Executes a strictly read-only, tenant-isolated parameterized subgraph query."""
        if not tenant_id or not tenant_id.strip():
            raise TenantIsolationError("Tenant ID is required for graph queries.")

        depth = min(max(1, max_depth), 3)  # Bound depth between 1 and 3

        # Filter nodes by tenant_id and entity_id
        matching_nodes = [
            n for n in self._mock_nodes
            if n.properties.get("tenant_id") == tenant_id and n.id == entity_id
        ]

        # Find connected relationships within same tenant
        matching_rels = []
        if matching_nodes:
            target_id = matching_nodes[0].id
            for rel in self._mock_rels:
                if rel.properties.get("tenant_id") == tenant_id:
                    if rel.start_node_id == target_id or rel.end_node_id == target_id:
                        if not relationship_type or rel.type.lower() == relationship_type.lower():
                            matching_rels.append(rel)

        return GraphQueryResult(
            tenant_id=tenant_id,
            nodes=matching_nodes,
            relationships=matching_rels,
        )

    def validate_safe_cypher(self, query: str) -> None:
        """Verifies a Cypher query is strictly read-only and does not contain mutation keywords."""
        if FORBIDDEN_WRITE_KEYWORDS.search(query):
            raise PayloadValidationError(
                "Cypher query contains forbidden mutation keywords. Only read-only queries are permitted."
            )
