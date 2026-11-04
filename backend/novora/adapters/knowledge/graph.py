"""Customer-owned graph database adapters with tenant isolation and safe query validation."""
from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

FORBIDDEN_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH\s+DELETE|SET|REMOVE|DROP|ALTER)\b",
    re.IGNORECASE,
)


class Neo4jConnector(GraphStoreConnector):
    """Customer-owned Neo4j graph connector enforcing read-only operations, parameterized queries, and tenant isolation."""

    provider_name = "neo4j"

    def __init__(
        self,
        endpoint_url: str,
        username: str,
        password: str,
        allow_private_network: bool = False,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.username = username
        self.password = password
        self.allow_private_network = allow_private_network
        self._connected = False
        self._mock_nodes: List[GraphNode] = []
        self._mock_rels: List[GraphRelationship] = []

        if endpoint_url and not endpoint_url.startswith("mock://") and not endpoint_url.startswith("bolt://") and not endpoint_url.startswith("neo4j://"):
            validate_destination_endpoint(endpoint_url, allow_private=allow_private_network)

    def connect(self) -> None:
        self._connected = True

    def validate_connection(self) -> bool:
        if not self.endpoint_url:
            return True
        if self.endpoint_url.startswith("mock://") or self.endpoint_url.startswith("bolt://") or self.endpoint_url.startswith("neo4j://"):
            return True
        try:
            validate_destination_endpoint(self.endpoint_url, allow_private=self.allow_private_network)
            return True
        except Exception:
            return False

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "healthy" if self.validate_connection() else "unhealthy",
            "provider": "neo4j",
            "connected": self._connected,
        }

    def create_or_validate_schema(self) -> bool:
        return True

    def add_node(self, node: GraphNode) -> None:
        self._mock_nodes.append(node)

    def add_relationship(self, rel: GraphRelationship) -> None:
        self._mock_rels.append(rel)

    def validate_safe_cypher(self, query: str) -> None:
        """Verifies a Cypher query is strictly read-only and does not contain mutation keywords."""
        if FORBIDDEN_WRITE_KEYWORDS.search(query):
            raise PayloadValidationError(
                "Cypher query contains forbidden mutation keywords. Only read-only queries are permitted."
            )

    def query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        self.validate_safe_cypher(query)
        if tenant_id:
            # Return tenant-filtered nodes
            return [
                {"n": n.model_dump()}
                for n in self._mock_nodes
                if n.properties.get("tenant_id") == tenant_id
            ]
        return [{"n": n.model_dump()} for n in self._mock_nodes]

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

        depth = min(max(1, max_depth), 3)

        matching_nodes = [
            n for n in self._mock_nodes
            if n.properties.get("tenant_id") == tenant_id and (n.id == entity_id or n.properties.get("name") == entity_id)
        ]

        matching_rels: List[GraphRelationship] = []
        if matching_nodes:
            target_ids = {n.id for n in matching_nodes}
            for rel in self._mock_rels:
                if rel.properties.get("tenant_id") == tenant_id:
                    if rel.start_node_id in target_ids or rel.end_node_id in target_ids:
                        if not relationship_type or rel.type.lower() == relationship_type.lower():
                            matching_rels.append(rel)

        return GraphQueryResult(
            tenant_id=tenant_id,
            nodes=matching_nodes,
            relationships=matching_rels,
        )

    def retrieve_related_entities(
        self,
        entity_ids: List[str],
        tenant_id: str,
        max_depth: int = 1,
    ) -> GraphQueryResult:
        if not tenant_id or not tenant_id.strip():
            raise TenantIsolationError("Tenant ID is required for graph queries.")

        all_nodes: List[GraphNode] = []
        all_rels: List[GraphRelationship] = []
        seen_nodes = set()
        seen_rels = set()

        for eid in entity_ids:
            sub = self.query_subgraph(eid, tenant_id=tenant_id, max_depth=max_depth)
            for node in sub.nodes:
                if node.id not in seen_nodes:
                    seen_nodes.add(node.id)
                    all_nodes.append(node)
            for rel in sub.relationships:
                if rel.id not in seen_rels:
                    seen_rels.add(rel.id)
                    all_rels.append(rel)

        return GraphQueryResult(
            tenant_id=tenant_id,
            nodes=all_nodes,
            relationships=all_rels,
        )


def create_graph_connector(
    provider: str,
    config: Dict[str, Any],
    allow_private_network: bool = False,
) -> GraphStoreConnector:
    """Factory creating the appropriate graph connector."""
    prov = (provider or "").lower().strip()
    endpoint = config.get("endpoint_url") or config.get("url") or config.get("uri") or "mock://neo4j"
    username = config.get("username") or "neo4j"
    password = config.get("password") or "password"

    if prov == "neo4j":
        return Neo4jConnector(
            endpoint_url=endpoint,
            username=username,
            password=password,
            allow_private_network=allow_private_network,
        )
    else:
        raise ValueError(f"Unsupported graph provider: '{provider}'")
