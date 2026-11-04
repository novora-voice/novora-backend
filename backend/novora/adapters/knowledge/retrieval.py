"""Provider-neutral retrieval service supporting Vector, Graph, and Hybrid RAG."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from novora.adapters.knowledge.base import (
    VectorDocument,
    VectorSearchRequest,
    VectorStoreConnector,
)
from novora.adapters.knowledge.embeddings import EmbeddingService
from novora.adapters.knowledge.graph import create_graph_connector
from novora.adapters.knowledge.vector import create_vector_connector
from novora.core.enums import RetrievalMode
from novora.core.exceptions import TenantIsolationError
from novora.core.models import RetrievalEvidence, RetrievalTrace
from novora.persistence.models import DBKnowledgeBase
from novora.persistence.secrets import SecretManager

logger = logging.getLogger(__name__)


class KnowledgeRetrievalService:
    """Orchestrates vector, graph, and hybrid retrieval across customer-owned databases."""

    def __init__(self, embedding_service: Optional[EmbeddingService] = None) -> None:
        self.embeddings = embedding_service or EmbeddingService()

    def retrieve(
        self,
        kb: DBKnowledgeBase,
        query: str,
        org_id: str,
        retrieval_mode: str = "vector",
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
        max_graph_depth: int = 1,
    ) -> RetrievalTrace:
        """Execute retrieval matching the requested retrieval mode with strict tenant isolation."""
        if not org_id or not kb.org_id or kb.org_id != org_id:
            raise TenantIsolationError(
                f"Tenant isolation error: Knowledge Base '{kb.id}' does not belong to organization '{org_id}'."
            )

        start_time = time.time()
        mode_val = (retrieval_mode or "vector").lower()

        evidence_items: List[RetrievalEvidence] = []
        graph_entities: List[Dict[str, Any]] = []
        graph_relationships: List[Dict[str, Any]] = []

        # 1. Vector Retrieval
        if mode_val in ("vector", "hybrid"):
            vector_evidence = self._retrieve_vector(
                kb=kb,
                query=query,
                org_id=org_id,
                top_k=top_k,
                filter_metadata=filter_metadata,
            )
            evidence_items.extend(vector_evidence)

        # 2. Graph Retrieval
        if mode_val in ("graph", "hybrid") and kb.graph_provider:
            g_entities, g_rels, graph_evidence = self._retrieve_graph(
                kb=kb,
                query=query,
                org_id=org_id,
                max_depth=max_graph_depth,
            )
            graph_entities.extend(g_entities)
            graph_relationships.extend(g_rels)
            evidence_items.extend(graph_evidence)

        # 3. Deduplicate and sort evidence
        deduped: Dict[str, RetrievalEvidence] = {}
        for item in evidence_items:
            key = f"{item.document_id}:{item.chunk_id}"
            if key not in deduped or item.score > deduped[key].score:
                deduped[key] = item

        sorted_evidence = sorted(deduped.values(), key=lambda x: x.score, reverse=True)[:top_k]
        latency_ms = round((time.time() - start_time) * 1000.0, 2)

        return RetrievalTrace(
            query=query,
            org_id=org_id,
            knowledge_base_ids=[kb.id],
            retrieval_mode=mode_val,
            evidence=sorted_evidence,
            graph_entities=graph_entities,
            graph_relationships=graph_relationships,
            latency_ms=latency_ms,
        )

    def _get_vector_connector(self, kb: DBKnowledgeBase) -> VectorStoreConnector:
        decrypted_json = SecretManager.decode_credential(kb.vector_config_encrypted)
        config = json.loads(decrypted_json) if decrypted_json else {}
        return create_vector_connector(kb.vector_provider, config)

    def _retrieve_vector(
        self,
        kb: DBKnowledgeBase,
        query: str,
        org_id: str,
        top_k: int,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievalEvidence]:
        connector = self._get_vector_connector(kb)
        query_vector = self.embeddings.embed_query(query, model=kb.embedding_model)

        search_req = VectorSearchRequest(
            tenant_id=org_id,
            query_text=query,
            query_vector=query_vector,
            top_k=top_k,
            filter_metadata=filter_metadata or {},
            namespace=kb.namespace,
        )
        vector_docs = connector.search(search_req)

        results: List[RetrievalEvidence] = []
        for doc in vector_docs:
            doc_id = doc.metadata.get("document_id") or doc.id.split("_chunk_")[0]
            chunk_id = doc.id
            results.append(
                RetrievalEvidence(
                    document_id=doc_id,
                    chunk_id=chunk_id,
                    text=doc.text,
                    score=doc.score,
                    metadata=doc.metadata,
                    source="vector",
                )
            )
        return results

    def _retrieve_graph(
        self,
        kb: DBKnowledgeBase,
        query: str,
        org_id: str,
        max_depth: int = 1,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[RetrievalEvidence]]:
        if not kb.graph_config_encrypted or not kb.graph_provider:
            return [], [], []

        decrypted_json = SecretManager.decode_credential(kb.graph_config_encrypted)
        config = json.loads(decrypted_json) if decrypted_json else {}
        connector = create_graph_connector(kb.graph_provider, config)

        # Extract potential entity candidates from query words
        words = [w.strip() for w in query.split() if len(w.strip()) > 3]
        subgraph = connector.retrieve_related_entities(words, tenant_id=org_id, max_depth=max_depth)

        entities = [n.model_dump() for n in subgraph.nodes]
        rels = [r.model_dump() for r in subgraph.relationships]

        evidence: List[RetrievalEvidence] = []
        for n in subgraph.nodes:
            props_str = ", ".join(f"{k}: {v}" for k, v in n.properties.items() if k != "tenant_id")
            evidence.append(
                RetrievalEvidence(
                    document_id=f"graph_{n.id}",
                    chunk_id=f"node_{n.id}",
                    text=f"Entity [{', '.join(n.labels)}]: {props_str}",
                    score=0.85,
                    metadata={"entity_id": n.id, "labels": n.labels},
                    source="graph",
                )
            )

        return entities, rels, evidence

