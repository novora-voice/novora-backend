"""Document ingestion pipeline: parsing, chunking, embedding, and indexing."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from novora.adapters.knowledge.base import VectorDocument
from novora.adapters.knowledge.embeddings import EmbeddingService
from novora.adapters.knowledge.graph import GraphNode, create_graph_connector
from novora.adapters.knowledge.parser import chunk_text, extract_text_from_file, normalize_text
from novora.adapters.knowledge.vector import create_vector_connector
from novora.core.enums import DocumentStatus
from novora.core.exceptions import PayloadValidationError, TenantIsolationError
from novora.persistence.models import DBKnowledgeBase, DBKnowledgeDocument
from novora.persistence.secrets import SecretManager

logger = logging.getLogger(__name__)

STORAGE_BASE_DIR = Path(__file__).resolve().parents[3] / "storage" / "documents"
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB


class DocumentIngestionPipeline:
    """Manages secure document persistence, parsing, chunking, embedding, and indexing."""

    def __init__(self, embedding_service: Optional[EmbeddingService] = None) -> None:
        self.embeddings = embedding_service or EmbeddingService()

    def process_and_index(
        self,
        kb: DBKnowledgeBase,
        doc: DBKnowledgeDocument,
        content: bytes,
        db: Session,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> int:
        """Process raw document content, generate chunks, embed, and index into customer's vector database."""
        if not doc.org_id or kb.org_id != doc.org_id:
            raise TenantIsolationError("Tenant isolation mismatch between document and knowledge base.")

        if len(content) > MAX_FILE_SIZE:
            doc.status = DocumentStatus.FAILED.value
            doc.error_message = f"File size exceeds maximum permitted limit ({MAX_FILE_SIZE // (1024*1024)}MB)."
            db.commit()
            raise PayloadValidationError(doc.error_message)

        doc.status = DocumentStatus.PROCESSING.value
        db.commit()

        try:
            # 1. Save file to local storage abstraction
            storage_path = self._save_file(doc.org_id, kb.id, doc.id, content, doc.filename)
            doc.storage_path = str(storage_path)

            # 2. Extract and normalize text
            raw_text = extract_text_from_file(content, doc.filename, doc.mime_type)
            clean_text = normalize_text(raw_text)

            if not clean_text:
                raise ValueError("No extractable text found in uploaded document.")

            # 3. Chunking
            chunks = chunk_text(clean_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            if not chunks:
                chunks = [clean_text]

            # 4. Generate embeddings
            embeddings = self.embeddings.embed_documents(chunks, model=kb.embedding_model)

            # 5. Build VectorDocument objects
            vector_docs: List[VectorDocument] = []
            for idx, (chunk_str, emb) in enumerate(zip(chunks, embeddings)):
                vdoc = VectorDocument(
                    id=f"{doc.id}_chunk_{idx}",
                    text=chunk_str,
                    tenant_id=doc.org_id,
                    embedding=emb,
                    metadata={
                        "document_id": doc.id,
                        "knowledge_base_id": kb.id,
                        "filename": doc.filename,
                        "chunk_index": idx,
                        "total_chunks": len(chunks),
                    },
                )
                vector_docs.append(vdoc)

            # 6. Index into vector store
            decrypted_json = SecretManager.decode_credential(kb.vector_config_encrypted)
            v_config = json.loads(decrypted_json) if decrypted_json else {}
            vector_connector = create_vector_connector(kb.vector_provider, v_config)
            vector_connector.upsert_documents(vector_docs, collection_name=kb.collection_name)

            # 7. Optional graph indexing (extract simple entities)
            if kb.graph_provider and kb.graph_config_encrypted:
                try:
                    self._index_graph_entities(kb, doc, chunks)
                except Exception as g_exc:
                    logger.warning("Graph indexing failed (continuing with vector only): %s", g_exc)

            # 8. Update document status
            doc.status = DocumentStatus.INDEXED.value
            doc.chunk_count = len(chunks)
            doc.error_message = None

            # Update KB document count
            kb.document_count = (
                db.query(DBKnowledgeDocument)
                .filter(
                    DBKnowledgeDocument.knowledge_base_id == kb.id,
                    DBKnowledgeDocument.status == DocumentStatus.INDEXED.value,
                )
                .count()
            )
            db.commit()

            return len(chunks)

        except Exception as exc:
            logger.error("Document ingestion failed for doc %s: %s", doc.id, exc, exc_info=True)
            doc.status = DocumentStatus.FAILED.value
            doc.error_message = str(exc)
            db.commit()
            raise

    def delete_document_index(self, kb: DBKnowledgeBase, doc: DBKnowledgeDocument, db: Session) -> None:
        """Remove document chunks from vector index and delete local file storage."""
        try:
            decrypted_json = SecretManager.decode_credential(kb.vector_config_encrypted)
            v_config = json.loads(decrypted_json) if decrypted_json else {}
            vector_connector = create_vector_connector(kb.vector_provider, v_config)
            vector_connector.delete_documents([doc.id], tenant_id=doc.org_id, collection_name=kb.collection_name)
        except Exception as exc:
            logger.warning("Failed to delete chunks from vector store for doc %s: %s", doc.id, exc)

        # Remove local file if present
        if doc.storage_path and os.path.exists(doc.storage_path):
            try:
                os.remove(doc.storage_path)
            except Exception as f_exc:
                logger.warning("Could not delete file %s: %s", doc.storage_path, f_exc)

    def _save_file(self, org_id: str, kb_id: str, doc_id: str, content: bytes, filename: str) -> Path:
        target_dir = STORAGE_BASE_DIR / org_id / kb_id
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{doc_id}_{filename.replace('/', '_').replace('\\\\', '_')}"
        file_path = target_dir / safe_name
        file_path.write_bytes(content)
        return file_path

    def _index_graph_entities(self, kb: DBKnowledgeBase, doc: DBKnowledgeDocument, chunks: List[str]) -> None:
        decrypted_json = SecretManager.decode_credential(kb.graph_config_encrypted)
        g_config = json.loads(decrypted_json) if decrypted_json else {}
        graph_connector = create_graph_connector(kb.graph_provider, g_config)

        # Create document node
        doc_node = GraphNode(
            id=doc.id,
            labels=["Document"],
            properties={
                "name": doc.filename,
                "tenant_id": doc.org_id,
                "document_id": doc.id,
            },
        )
        if hasattr(graph_connector, "add_node"):
            graph_connector.add_node(doc_node)

