"""Comprehensive tests for customer-owned knowledge base infrastructure, adapters, RBAC, retrieval, and evaluation."""
import json
import pytest
from unittest.mock import MagicMock, patch

from novora.adapters.knowledge.base import (
    GraphNode,
    GraphRelationship,
    VectorDocument,
    VectorSearchRequest,
)
from novora.adapters.knowledge.embeddings import EmbeddingService
from novora.adapters.knowledge.graph import Neo4jConnector, create_graph_connector
from novora.adapters.knowledge.parser import chunk_text, extract_text_from_file, normalize_text
from novora.adapters.knowledge.vector import (
    ChromaConnector,
    PineconeConnector,
    QdrantConnector,
    WeaviateConnector,
    create_vector_connector,
)
from novora.core.enums import MessageRole, OrgRole, OverallStatus, RuleStatus, RuleType
from novora.core.exceptions import PayloadValidationError, SSRFSecurityError, TenantIsolationError
from novora.core.models import (
    Conversation,
    ConversationMessage,
    EvaluationScenario,
    RuleConfig,
)
from novora.core.rbac import (
    has_sufficient_role,
    verify_tenant_isolation,
)
from novora.evaluation.engine import EvaluationEngine
from novora.evaluation.rules.knowledge_rules import (
    KnowledgeGroundednessRule,
    KnowledgeRetrievalSufficiencyRule,
    KnowledgeSourceCitationRule,
    KnowledgeTenantAuthorizationRule,
)


# ---------------------------------------------------------------------------
# 1. Vector Database Adapters & Factory Tests
# ---------------------------------------------------------------------------

class TestVectorAdapters:
    def test_chroma_crud_and_isolation(self):
        connector = ChromaConnector(endpoint_url="mock://chroma", collection_name="test_col")
        connector.connect()
        assert connector.validate_connection() is True
        assert connector.health_check()["status"] == "healthy"

        # Upsert documents for tenant A
        doc1 = VectorDocument(id="doc_1", text="Novora voice agent evaluation", tenant_id="org_a", metadata={"product": "voice"})
        doc2 = VectorDocument(id="doc_2", text="Customer refund limit is 50 dollars", tenant_id="org_a")
        # Upsert document for tenant B
        doc3 = VectorDocument(id="doc_3", text="Competitor confidential policy", tenant_id="org_b")

        count = connector.upsert_documents([doc1, doc2, doc3])
        assert count == 3

        # Search tenant A — must NOT return tenant B document
        req_a = VectorSearchRequest(tenant_id="org_a", query_text="refund", top_k=5)
        res_a = connector.search(req_a)
        assert len(res_a) == 1
        assert res_a[0].id == "doc_2"
        assert res_a[0].tenant_id == "org_a"

        # Search tenant B
        req_b = VectorSearchRequest(tenant_id="org_b", query_text="policy", top_k=5)
        res_b = connector.search(req_b)
        assert len(res_b) == 1
        assert res_b[0].id == "doc_3"

        # Missing tenant_id must raise TenantIsolationError
        with pytest.raises(TenantIsolationError):
            connector.search(VectorSearchRequest.model_construct(tenant_id="", query_text="refund"))

        # Deletion
        del_count = connector.delete_documents(["doc_1"], tenant_id="org_a")
        assert del_count == 1
        assert len(connector.search(VectorSearchRequest(tenant_id="org_a", top_k=10))) == 1

    def test_pinecone_adapter(self):
        connector = PineconeConnector(
            endpoint_url="https://index-abc.pinecone.io",
            api_key="mock_secret_key",
            index_name="kb-index",
            allow_private_network=True,
        )
        doc = VectorDocument(id="p_1", text="Pinecone high performance vector search", tenant_id="org_pine")
        connector.upsert_documents([doc])
        results = connector.search(VectorSearchRequest(tenant_id="org_pine", query_text="vector search"))
        assert len(results) == 1
        assert "Pinecone" in results[0].text

    def test_weaviate_adapter(self):
        connector = WeaviateConnector(
            endpoint_url="https://cluster.weaviate.network",
            api_key="mock_key",
            collection_name="Articles",
            allow_private_network=True,
        )
        doc = VectorDocument(id="w_1", text="Weaviate hybrid search schema", tenant_id="org_weav")
        connector.upsert_documents([doc])
        results = connector.search(VectorSearchRequest(tenant_id="org_weav", query_text="hybrid"))
        assert len(results) == 1

    def test_qdrant_adapter(self):
        connector = QdrantConnector(
            endpoint_url="https://qdrant.example.com:6333",
            collection_name="q_col",
            allow_private_network=True,
        )
        doc = VectorDocument(id="q_1", text="Qdrant payload filtering and vectors", tenant_id="org_q")
        connector.upsert_documents([doc])
        results = connector.search(VectorSearchRequest(tenant_id="org_q", query_text="payload"))
        assert len(results) == 1

    def test_create_vector_connector_factory(self):
        for prov in ("chroma", "pinecone", "weaviate", "qdrant"):
            conn = create_vector_connector(prov, {"collection_name": "test"}, allow_private_network=True)
            assert conn is not None
            assert conn.validate_connection() is True

        with pytest.raises(ValueError, match="Unsupported vector provider"):
            create_vector_connector("invalid_provider", {})


# ---------------------------------------------------------------------------
# 2. Graph Database Adapter Tests
# ---------------------------------------------------------------------------

class TestGraphAdapter:
    def test_neo4j_subgraph_and_isolation(self):
        connector = Neo4jConnector(
            endpoint_url="mock://neo4j",
            username="neo4j",
            password="password",
            allow_private_network=True,
        )
        connector.connect()
        assert connector.validate_connection() is True

        # Add nodes
        n1 = GraphNode(id="refund_policy", labels=["Policy"], properties={"tenant_id": "org_graph", "name": "Refund Policy"})
        n2 = GraphNode(id="order_1001", labels=["Order"], properties={"tenant_id": "org_graph", "name": "ORD-1001"})
        n_other = GraphNode(id="secret_order", labels=["Order"], properties={"tenant_id": "other_org", "name": "Confidential"})

        connector.add_node(n1)
        connector.add_node(n2)
        connector.add_node(n_other)

        # Add relationship
        r1 = GraphRelationship(
            id="rel_1",
            type="GOVERNED_BY",
            start_node_id="order_1001",
            end_node_id="refund_policy",
            properties={"tenant_id": "org_graph"},
        )
        connector.add_relationship(r1)

        # Query subgraph for tenant
        res = connector.query_subgraph("order_1001", tenant_id="org_graph")
        assert len(res.nodes) == 1
        assert res.nodes[0].id == "order_1001"
        assert len(res.relationships) == 1
        assert res.relationships[0].type == "GOVERNED_BY"

        # Tenant isolation: query with different tenant must not see org_graph data
        res_empty = connector.query_subgraph("order_1001", tenant_id="other_org")
        assert len(res_empty.nodes) == 0

        # Cypher read-only validation
        connector.validate_safe_cypher("MATCH (n:Policy) RETURN n")
        with pytest.raises(PayloadValidationError):
            connector.validate_safe_cypher("MATCH (n) DELETE n")
        with pytest.raises(PayloadValidationError):
            connector.validate_safe_cypher("CREATE (n:Policy {name: 'fake'})")

    def test_create_graph_connector_factory(self):
        conn = create_graph_connector("neo4j", {"url": "mock://neo4j"}, allow_private_network=True)
        assert isinstance(conn, Neo4jConnector)
        with pytest.raises(ValueError):
            create_graph_connector("unsupported_graph", {})


# ---------------------------------------------------------------------------
# 3. Document Parsing & Chunking Tests
# ---------------------------------------------------------------------------

class TestDocumentParser:
    def test_extract_plaintext(self):
        raw = b"Hello, this is a plain text knowledge document.\nSecond line."
        text = extract_text_from_file(raw, "notes.txt", "text/plain")
        assert "Hello, this is a plain text" in text
        assert "Second line." in text

    def test_extract_csv(self):
        raw = b"PolicyID,MaxAmount,Condition\nPOL-1,50,Damaged Item\nPOL-2,100,Lost Item"
        text = extract_text_from_file(raw, "policies.csv", "text/csv")
        assert "POL-1" in text
        assert "MaxAmount: 50" in text

    def test_normalize_text(self):
        messy = "Hello   \r\n\r\n\r\n   world! \u200B  Extra   spaces.  "
        clean = normalize_text(messy)
        assert clean == "Hello\n\nworld! Extra spaces."

    def test_chunking(self):
        long_text = "Sentence one. " * 50  # ~700 characters
        chunks = chunk_text(long_text, chunk_size=200, chunk_overlap=30)
        assert len(chunks) > 1
        for ch in chunks:
            assert len(ch) <= 250


# ---------------------------------------------------------------------------
# 4. Embedding Service Tests
# ---------------------------------------------------------------------------

class TestEmbeddingService:
    def test_deterministic_fallback_vectors(self):
        service = EmbeddingService(api_token=None)
        v1 = service.embed_query("refund policy")
        v2 = service.embed_query("refund policy")
        v3 = service.embed_query("shipping policy")

        # Deterministic: identical texts give identical vectors
        assert v1 == v2
        # Different texts give different vectors
        assert v1 != v3
        assert len(v1) == 384

    def test_model_compatibility(self):
        assert EmbeddingService.validate_compatibility("all-MiniLM-L6-v2", "sentence-transformers/all-MiniLM-L6-v2") is True
        assert EmbeddingService.validate_compatibility("bge-small-en-v1.5", "BAAI/bge-small-en-v1.5") is True
        assert EmbeddingService.validate_compatibility("all-MiniLM-L6-v2", "bge-small-en") is False


# ---------------------------------------------------------------------------
# 5. RBAC & Tenant Isolation Tests
# ---------------------------------------------------------------------------

class TestRBAC:
    def test_role_hierarchy(self):
        assert has_sufficient_role("owner", OrgRole.VIEWER) is True
        assert has_sufficient_role("owner", OrgRole.ADMIN) is True
        assert has_sufficient_role("admin", OrgRole.MEMBER) is True
        assert has_sufficient_role("member", OrgRole.ADMIN) is False
        assert has_sufficient_role("viewer", OrgRole.MEMBER) is False

    def test_verify_tenant_isolation(self):
        # Matching tenant passes
        verify_tenant_isolation("org_123", "org_123", "Document")

        # Mismatch raises TenantIsolationError
        with pytest.raises(TenantIsolationError):
            verify_tenant_isolation("org_123", "org_999", "Document")


# ---------------------------------------------------------------------------
# 6. Knowledge-Grounded Evaluation Rules Tests
# ---------------------------------------------------------------------------

class TestKnowledgeEvaluationRules:
    def _make_conversation(self, messages_data, trace=None, org_id="org_test"):
        msgs = [
            ConversationMessage(role=m[0], content=m[1], sequence=i)
            for i, m in enumerate(messages_data)
        ]
        metadata = {"org_id": org_id}
        if trace:
            metadata["retrieval_trace"] = trace
        return Conversation(scenario_id="scen_kb_test", messages=msgs, metadata=metadata)

    def test_retrieval_sufficiency_pass(self):
        rule = KnowledgeRetrievalSufficiencyRule()
        config = RuleConfig(rule_type=RuleType.KNOWLEDGE_RETRIEVAL_SUFFICIENCY, parameters={"min_chunks": 1, "min_score": 0.5})
        trace = {
            "evidence": [
                {"document_id": "doc_1", "chunk_id": "c_1", "text": "Refunds up to $50 permitted.", "score": 0.85}
            ]
        }
        conv = self._make_conversation([(MessageRole.AGENT, "We can credit up to $50.")], trace=trace)
        res = rule.evaluate(config, conv, EvaluationScenario(name="Test", business_goal="Goal"))
        assert res.status == RuleStatus.PASS

    def test_retrieval_sufficiency_missing_trace(self):
        rule = KnowledgeRetrievalSufficiencyRule()
        config = RuleConfig(rule_type=RuleType.KNOWLEDGE_RETRIEVAL_SUFFICIENCY)
        conv = self._make_conversation([(MessageRole.AGENT, "Hello")])
        res = rule.evaluate(config, conv, EvaluationScenario(name="Test", business_goal="Goal"))
        assert res.status == RuleStatus.FAIL
        assert "No retrieval trace" in res.explanation

    def test_groundedness_pass(self):
        rule = KnowledgeGroundednessRule()
        config = RuleConfig(
            rule_type=RuleType.KNOWLEDGE_GROUNDEDNESS,
            parameters={"prohibited_unsupported_claims": ["100% money back guarantee"]},
        )
        trace = {
            "evidence": [
                {"document_id": "doc_1", "text": "Returns within 30 days are accepted.", "score": 0.9}
            ]
        }
        conv = self._make_conversation([(MessageRole.AGENT, "Returns within 30 days are accepted.")], trace=trace)
        res = rule.evaluate(config, conv, EvaluationScenario(name="Test", business_goal="Goal"))
        assert res.status == RuleStatus.PASS

    def test_groundedness_fail_on_hallucinated_claim(self):
        rule = KnowledgeGroundednessRule()
        config = RuleConfig(
            rule_type=RuleType.KNOWLEDGE_GROUNDEDNESS,
            parameters={"prohibited_unsupported_claims": ["100% money back guarantee"]},
        )
        trace = {
            "evidence": [
                {"document_id": "doc_1", "text": "Standard return policy is 30 days.", "score": 0.9}
            ]
        }
        conv = self._make_conversation(
            [(MessageRole.AGENT, "I promise a 100% money back guarantee on everything!")],
            trace=trace,
        )
        res = rule.evaluate(config, conv, EvaluationScenario(name="Test", business_goal="Goal"))
        assert res.status == RuleStatus.FAIL
        assert "not supported" in res.explanation.lower()

    def test_tenant_authorization_rule_pass(self):
        rule = KnowledgeTenantAuthorizationRule()
        config = RuleConfig(
            rule_type=RuleType.KNOWLEDGE_TENANT_AUTHORIZATION,
            parameters={"authorized_org_id": "org_secure"},
        )
        trace = {
            "org_id": "org_secure",
            "evidence": [{"document_id": "doc_1", "metadata": {"tenant_id": "org_secure"}}],
        }
        conv = self._make_conversation([(MessageRole.AGENT, "Data")], trace=trace, org_id="org_secure")
        res = rule.evaluate(config, conv, EvaluationScenario(name="Test", business_goal="Goal"))
        assert res.status == RuleStatus.PASS

    def test_tenant_authorization_rule_violation(self):
        rule = KnowledgeTenantAuthorizationRule()
        config = RuleConfig(
            rule_type=RuleType.KNOWLEDGE_TENANT_AUTHORIZATION,
            parameters={"authorized_org_id": "org_secure"},
        )
        # Trace belongs to another tenant!
        trace = {
            "org_id": "org_hacker",
            "evidence": [{"document_id": "doc_foreign", "metadata": {"tenant_id": "org_hacker"}}],
        }
        conv = self._make_conversation([(MessageRole.AGENT, "Data")], trace=trace, org_id="org_secure")
        res = rule.evaluate(config, conv, EvaluationScenario(name="Test", business_goal="Goal"))
        assert res.status == RuleStatus.FAIL
        assert "CRITICAL" in res.explanation

    def test_evaluation_engine_includes_knowledge_rules(self):
        engine = EvaluationEngine()
        assert RuleType.KNOWLEDGE_RETRIEVAL_SUFFICIENCY in engine._evaluators
        assert RuleType.KNOWLEDGE_GROUNDEDNESS in engine._evaluators
        assert RuleType.KNOWLEDGE_SOURCE_CITATION in engine._evaluators
        assert RuleType.KNOWLEDGE_TENANT_AUTHORIZATION in engine._evaluators
