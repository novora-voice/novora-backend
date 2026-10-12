import pytest
from novora.adapters.knowledge.base import (
    GraphNode,
    GraphRelationship,
    VectorDocument,
    VectorSearchRequest,
)
from novora.adapters.knowledge.graph import Neo4jConnector
from novora.adapters.knowledge.vector import PineconeConnector
from novora.core.exceptions import PayloadValidationError, TenantIsolationError

def test_vector_connector_tenant_isolation():
    connector = PineconeConnector(
        endpoint_url="https://index-123.pinecone.io",
        api_key="pinecone_key",
        index_name="policies",
        allow_private_network=True,
    )

    # Seed data for Tenant A and Tenant B
    connector.add_document(
        VectorDocument(
            id="doc_a1",
            text="Tenant A refund policy: maximum $50 credit allowed.",
            tenant_id="tenant_a",
        )
    )
    connector.add_document(
        VectorDocument(
            id="doc_b1",
            text="Tenant B refund policy: maximum $500 VIP credit allowed.",
            tenant_id="tenant_b",
        )
    )

    # Search as Tenant A
    req_a = VectorSearchRequest(
        tenant_id="tenant_a",
        query_text="refund policy",
    )
    results_a = connector.search(req_a)
    assert len(results_a) == 1
    assert results_a[0].id == "doc_a1"
    assert "Tenant A" in results_a[0].text

    # Search with missing tenant_id raises TenantIsolationError
    with pytest.raises(TenantIsolationError):
        connector.search(VectorSearchRequest(tenant_id="  ", query_text="test"))

def test_graph_connector_read_only_and_tenant_isolation():
    connector = Neo4jConnector(
        endpoint_url="https://db-neo4j.customer.test:7687",
        username="neo4j",
        password="secret_password",
        allow_private_network=True,
    )

    # Seed nodes
    connector.add_node(
        GraphNode(
            id="policy_refund",
            labels=["Policy"],
            properties={"tenant_id": "tenant_1", "max_limit": 50},
        )
    )
    connector.add_node(
        GraphNode(
            id="tier_standard",
            labels=["Tier"],
            properties={"tenant_id": "tenant_1"},
        )
    )
    connector.add_relationship(
        GraphRelationship(
            id="rel_01",
            type="APPLIES_TO",
            start_node_id="policy_refund",
            end_node_id="tier_standard",
            properties={"tenant_id": "tenant_1"},
        )
    )

    # Query as tenant_1
    res = connector.query_subgraph(
        entity_id="policy_refund",
        tenant_id="tenant_1",
    )
    assert len(res.nodes) == 1
    assert len(res.relationships) == 1

    # Query as tenant_2 returns nothing
    res_other = connector.query_subgraph(
        entity_id="policy_refund",
        tenant_id="tenant_2",
    )
    assert len(res_other.nodes) == 0

    # Write keyword validation
    with pytest.raises(PayloadValidationError, match="forbidden mutation keywords"):
        connector.validate_safe_cypher("MATCH (n) DETACH DELETE n")

    with pytest.raises(PayloadValidationError, match="forbidden mutation keywords"):
        connector.validate_safe_cypher("CREATE (n:Policy {name: 'Test'})")
