"""Integration tests for Knowledge Base API, Document Ingestion, and RBAC routes."""
import json
import pytest
from starlette.testclient import TestClient

from novora.api.auth_utils import Base, engine, init_db
from novora.api.main import create_app
from novora.adapters.repositories import (
    InMemoryConversationRepository,
    InMemoryEvaluationRepository,
    InMemoryScenarioRepository,
)


@pytest.fixture
def api_client():
    init_db()
    conv_repo = InMemoryConversationRepository()
    scen_repo = InMemoryScenarioRepository(seed_defaults=False)
    eval_repo = InMemoryEvaluationRepository()
    app = create_app(
        scenario_repo=scen_repo,
        evaluation_repo=eval_repo,
        conversation_repo=conv_repo,
    )
    with TestClient(app) as client:
        yield client


def _create_user(client: TestClient, email: str, name: str) -> tuple[str, str]:
    """Helper to create user and return (user_id, auth_token)."""
    resp = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123!", "full_name": name},
    )
    assert resp.status_code == 201
    data = resp.json()
    return data["user"]["id"], data["access_token"]


class TestKnowledgeAndOrgAPI:
    def test_full_lifecycle_and_tenant_isolation(self, api_client):
        # 1. Create two users in different organizations
        user_a_id, token_a = _create_user(api_client, "alice@acme.com", "Alice Owner")
        user_b_id, token_b = _create_user(api_client, "bob@competitor.com", "Bob Rival")

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 2. Alice creates Organization A
        org_a_resp = api_client.post(
            "/api/v1/organizations",
            json={"name": "Acme Corp", "slug": "acme-corp"},
            headers=headers_a,
        )
        assert org_a_resp.status_code == 201
        org_a = org_a_resp.json()
        org_a_id = org_a["id"]
        assert org_a["role"] == "owner"

        # 3. Bob creates Organization B
        org_b_resp = api_client.post(
            "/api/v1/organizations",
            json={"name": "Competitor Inc", "slug": "competitor-inc"},
            headers=headers_b,
        )
        assert org_b_resp.status_code == 201
        org_b_id = org_b_resp.json()["id"]

        # 4. Connection validation endpoint
        val_resp = api_client.post(
            "/api/v1/knowledge-bases/validate-connection",
            json={
                "provider_type": "vector",
                "provider_name": "chroma",
                "config": {"collection_name": "acme_docs"},
            },
            headers=headers_a,
        )
        assert val_resp.status_code == 200
        assert val_resp.json()["valid"] is True

        # 5. Alice creates Knowledge Base in Org A
        kb_create_resp = api_client.post(
            "/api/v1/knowledge-bases",
            json={
                "org_id": org_a_id,
                "name": "Acme Customer Policies",
                "description": "Standard support procedures and refund caps.",
                "vector_provider": "chroma",
                "vector_config": {"collection_name": "acme_policies"},
                "collection_name": "acme_policies",
            },
            headers=headers_a,
        )
        assert kb_create_resp.status_code == 201
        kb_a = kb_create_resp.json()
        kb_a_id = kb_a["id"]
        assert kb_a["name"] == "Acme Customer Policies"
        assert kb_a["document_count"] == 0

        # 6. Bob attempts to access Alice's Knowledge Base -> 403 FORBIDDEN
        bob_access = api_client.get(
            f"/api/v1/knowledge-bases/{kb_a_id}",
            headers=headers_b,
        )
        assert bob_access.status_code == 403

        # 7. Alice uploads a document into her Knowledge Base
        doc_upload_resp = api_client.post(
            f"/api/v1/knowledge-bases/{kb_a_id}/documents",
            json={
                "filename": "refund_policy.txt",
                "content_text": "Acme Customer Refund Policy: Discretionary refunds are capped at $50.00 maximum per customer order. All refunds require manager authorization.",
                "mime_type": "text/plain",
            },
            headers=headers_a,
        )
        assert doc_upload_resp.status_code == 201
        doc_a = doc_upload_resp.json()
        assert doc_a["status"] == "indexed"
        assert doc_a["chunk_count"] >= 1

        # 8. List documents in KB
        docs_resp = api_client.get(
            f"/api/v1/knowledge-bases/{kb_a_id}/documents",
            headers=headers_a,
        )
        assert docs_resp.status_code == 200
        assert len(docs_resp.json()) == 1

        # 9. Test retrieval query in Org A
        ret_resp = api_client.post(
            f"/api/v1/knowledge-bases/{kb_a_id}/retrieve",
            json={"query": "maximum refund amount", "retrieval_mode": "vector", "top_k": 3},
            headers=headers_a,
        )
        assert ret_resp.status_code == 200
        trace = ret_resp.json()
        assert len(trace["evidence"]) >= 1
        assert "50.00" in trace["evidence"][0]["text"]
        assert trace["org_id"] == org_a_id

        # 10. Bob cannot query Alice's KB
        bob_ret = api_client.post(
            f"/api/v1/knowledge-bases/{kb_a_id}/retrieve",
            json={"query": "refund", "retrieval_mode": "vector"},
            headers=headers_b,
        )
        assert bob_ret.status_code == 403

        # 11. Test live connectivity
        test_conn_resp = api_client.post(
            f"/api/v1/knowledge-bases/{kb_a_id}/test-connection",
            headers=headers_a,
        )
        assert test_conn_resp.status_code == 200
        assert test_conn_resp.json()["status"] == "active"

        # 12. Delete document
        doc_del = api_client.delete(
            f"/api/v1/knowledge-bases/{kb_a_id}/documents/{doc_a['id']}",
            headers=headers_a,
        )
        assert doc_del.status_code == 204

        # Verify document count is 0
        kb_after = api_client.get(f"/api/v1/knowledge-bases/{kb_a_id}", headers=headers_a).json()
        assert kb_after["document_count"] == 0

