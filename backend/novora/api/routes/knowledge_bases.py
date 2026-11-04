"""Knowledge Base, customer-owned database connection, document ingestion, and retrieval API routes."""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from novora.api.auth import get_current_user
from novora.api.auth_utils import UserOrm, get_db
from novora.adapters.knowledge.graph import create_graph_connector
from novora.adapters.knowledge.ingestion import DocumentIngestionPipeline
from novora.adapters.knowledge.retrieval import KnowledgeRetrievalService
from novora.adapters.knowledge.vector import create_vector_connector
from novora.core.enums import DocumentStatus, OrgRole, VectorProvider
from novora.core.exceptions import TenantIsolationError
from novora.core.rbac import verify_org_access
from novora.persistence.models import DBKnowledgeBase, DBKnowledgeDocument
from novora.persistence.secrets import SecretManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["Knowledge Bases"])

_ingestion_pipeline = DocumentIngestionPipeline()
_retrieval_service = KnowledgeRetrievalService()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ValidateConnectionRequest(BaseModel):
    provider_type: str = Field(description="vector or graph")
    provider_name: str = Field(description="chroma, pinecone, weaviate, qdrant, neo4j")
    config: Dict[str, Any] = Field(default_factory=dict)


class CreateKnowledgeBaseRequest(BaseModel):
    org_id: str
    name: str = Field(min_length=1, max_length=128)
    description: Optional[str] = None
    vector_provider: str = Field(default="chroma")
    vector_config: Dict[str, Any] = Field(default_factory=dict)
    graph_provider: Optional[str] = None
    graph_config: Optional[Dict[str, Any]] = None
    embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    collection_name: str = Field(default="default")
    namespace: Optional[str] = None


class UpdateKnowledgeBaseRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    vector_config: Optional[Dict[str, Any]] = None
    graph_config: Optional[Dict[str, Any]] = None
    collection_name: Optional[str] = None
    namespace: Optional[str] = None


class KnowledgeBaseResponse(BaseModel):
    id: str
    org_id: str
    name: str
    description: Optional[str] = None
    vector_provider: str
    vector_config_masked: Dict[str, Any]
    graph_provider: Optional[str] = None
    graph_config_masked: Optional[Dict[str, Any]] = None
    embedding_model: str
    collection_name: str
    namespace: Optional[str] = None
    status: str
    document_count: int
    created_at: str
    updated_at: str


class DocumentResponse(BaseModel):
    id: str
    org_id: str
    knowledge_base_id: str
    filename: str
    mime_type: str
    file_size: int
    content_hash: str
    status: str
    chunk_count: int
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class DocumentUploadJsonRequest(BaseModel):
    filename: str
    content_text: Optional[str] = None
    content_base64: Optional[str] = None
    mime_type: str = "text/plain"


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1)
    retrieval_mode: str = Field(default="vector")  # vector, graph, hybrid
    top_k: int = Field(default=5, ge=1, le=50)
    filter_metadata: Dict[str, Any] = Field(default_factory=dict)
    max_graph_depth: int = Field(default=1, ge=1, le=3)


def _mask_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of config with secrets masked for safe frontend display."""
    masked = dict(config)
    for key in ("api_key", "apiKey", "password", "token", "secret"):
        if key in masked and masked[key]:
            masked[key] = SecretManager.mask_secret(str(masked[key]))
    return masked


def _to_kb_response(kb: DBKnowledgeBase) -> KnowledgeBaseResponse:
    v_raw = SecretManager.decode_credential(kb.vector_config_encrypted)
    v_cfg = json.loads(v_raw) if v_raw else {}

    g_cfg = None
    if kb.graph_config_encrypted:
        g_raw = SecretManager.decode_credential(kb.graph_config_encrypted)
        g_cfg = json.loads(g_raw) if g_raw else {}

    return KnowledgeBaseResponse(
        id=kb.id,
        org_id=kb.org_id,
        name=kb.name,
        description=kb.description,
        vector_provider=kb.vector_provider,
        vector_config_masked=_mask_config(v_cfg),
        graph_provider=kb.graph_provider,
        graph_config_masked=_mask_config(g_cfg) if g_cfg else None,
        embedding_model=kb.embedding_model,
        collection_name=kb.collection_name,
        namespace=kb.namespace,
        status=kb.status,
        document_count=kb.document_count,
        created_at=kb.created_at.isoformat() if kb.created_at else "",
        updated_at=kb.updated_at.isoformat() if kb.updated_at else "",
    )


# ---------------------------------------------------------------------------
# Connection Validation Endpoint
# ---------------------------------------------------------------------------

@router.post("/validate-connection")
def validate_database_connection(
    req: ValidateConnectionRequest,
    current_user: UserOrm = Depends(get_current_user),
) -> Dict[str, Any]:
    """Test connection credentials to a customer-owned vector or graph database before saving."""
    ptype = req.provider_type.lower().strip()
    pname = req.provider_name.lower().strip()

    try:
        if ptype == "vector":
            connector = create_vector_connector(pname, req.config)
            connector.connect()
            valid = connector.validate_connection()
            health = connector.health_check()
            return {"valid": valid, "provider": pname, "health": health}
        elif ptype == "graph":
            connector = create_graph_connector(pname, req.config)
            connector.connect()
            valid = connector.validate_connection()
            health = connector.health_check()
            return {"valid": valid, "provider": pname, "health": health}
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported provider_type: '{req.provider_type}'")
    except Exception as exc:
        logger.warning("Connection validation failed for %s/%s: %s", ptype, pname, exc)
        return {"valid": False, "provider": pname, "error": str(exc)}


# ---------------------------------------------------------------------------
# Knowledge Base CRUD Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
def create_knowledge_base(
    req: CreateKnowledgeBaseRequest,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeBaseResponse:
    """Create a new customer-owned Knowledge Base for an organization. Requires MEMBER role or higher."""
    verify_org_access(db, current_user.id, req.org_id, min_role=OrgRole.MEMBER)

    # Encrypt database connection secrets
    v_enc = SecretManager.encode_credential(json.dumps(req.vector_config))
    g_enc = SecretManager.encode_credential(json.dumps(req.graph_config)) if req.graph_config else None

    kb = DBKnowledgeBase(
        id=f"kb_{uuid.uuid4().hex[:12]}",
        org_id=req.org_id,
        name=req.name.strip(),
        description=req.description.strip() if req.description else None,
        vector_provider=req.vector_provider.lower(),
        vector_config_encrypted=v_enc,
        graph_provider=req.graph_provider.lower() if req.graph_provider else None,
        graph_config_encrypted=g_enc,
        embedding_model=req.embedding_model,
        collection_name=req.collection_name,
        namespace=req.namespace,
        status="active",
        document_count=0,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)

    return _to_kb_response(kb)


@router.get("", response_model=List[KnowledgeBaseResponse])
def list_knowledge_bases(
    org_id: str = Query(..., description="Organization ID to scope knowledge bases"),
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[KnowledgeBaseResponse]:
    """List all knowledge bases for an organization. Requires VIEWER role or higher."""
    verify_org_access(db, current_user.id, org_id, min_role=OrgRole.VIEWER)

    kbs = db.query(DBKnowledgeBase).filter(DBKnowledgeBase.org_id == org_id).all()
    return [_to_kb_response(kb) for kb in kbs]


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
def get_knowledge_base(
    kb_id: str,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeBaseResponse:
    """Get Knowledge Base details. Enforces organization tenant isolation."""
    kb = db.query(DBKnowledgeBase).filter(DBKnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found.")

    verify_org_access(db, current_user.id, kb.org_id, min_role=OrgRole.VIEWER)
    return _to_kb_response(kb)


@router.patch("/{kb_id}", response_model=KnowledgeBaseResponse)
def update_knowledge_base(
    kb_id: str,
    req: UpdateKnowledgeBaseRequest,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeBaseResponse:
    """Update Knowledge Base configuration. Requires MEMBER role or higher."""
    kb = db.query(DBKnowledgeBase).filter(DBKnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found.")

    verify_org_access(db, current_user.id, kb.org_id, min_role=OrgRole.MEMBER)

    if req.name is not None:
        kb.name = req.name.strip()
    if req.description is not None:
        kb.description = req.description.strip()
    if req.collection_name is not None:
        kb.collection_name = req.collection_name.strip()
    if req.namespace is not None:
        kb.namespace = req.namespace.strip()

    if req.vector_config is not None:
        kb.vector_config_encrypted = SecretManager.encode_credential(json.dumps(req.vector_config))
    if req.graph_config is not None:
        kb.graph_config_encrypted = SecretManager.encode_credential(json.dumps(req.graph_config))

    kb.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(kb)
    return _to_kb_response(kb)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base(
    kb_id: str,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a Knowledge Base and all its documents. Requires ADMIN role or higher."""
    kb = db.query(DBKnowledgeBase).filter(DBKnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found.")

    verify_org_access(db, current_user.id, kb.org_id, min_role=OrgRole.ADMIN)

    # Delete all documents in vector index
    docs = db.query(DBKnowledgeDocument).filter(DBKnowledgeDocument.knowledge_base_id == kb.id).all()
    for doc in docs:
        _ingestion_pipeline.delete_document_index(kb, doc, db)
        db.delete(doc)

    db.delete(kb)
    db.commit()


@router.post("/{kb_id}/test-connection")
def test_knowledge_base_connection(
    kb_id: str,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Test live connectivity of a saved Knowledge Base. Requires VIEWER role or higher."""
    kb = db.query(DBKnowledgeBase).filter(DBKnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found.")

    verify_org_access(db, current_user.id, kb.org_id, min_role=OrgRole.VIEWER)

    decrypted_v = SecretManager.decode_credential(kb.vector_config_encrypted)
    v_cfg = json.loads(decrypted_v) if decrypted_v else {}
    vector_conn = create_vector_connector(kb.vector_provider, v_cfg)
    v_health = vector_conn.health_check()

    g_health = None
    if kb.graph_provider and kb.graph_config_encrypted:
        decrypted_g = SecretManager.decode_credential(kb.graph_config_encrypted)
        g_cfg = json.loads(decrypted_g) if decrypted_g else {}
        graph_conn = create_graph_connector(kb.graph_provider, g_cfg)
        g_health = graph_conn.health_check()

    is_healthy = v_health.get("status") == "healthy" and (g_health is None or g_health.get("status") == "healthy")
    kb.status = "active" if is_healthy else "error"
    db.commit()

    return {
        "status": kb.status,
        "vector_health": v_health,
        "graph_health": g_health,
    }


# ---------------------------------------------------------------------------
# Document Management Endpoints
# ---------------------------------------------------------------------------

@router.post("/{kb_id}/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    kb_id: str,
    request: Request,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    """Upload and ingest a document. Supports JSON (text/base64) or multipart/form-data."""
    kb = db.query(DBKnowledgeBase).filter(DBKnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found.")

    verify_org_access(db, current_user.id, kb.org_id, min_role=OrgRole.MEMBER)

    content_type = request.headers.get("content-type", "")
    content_bytes: bytes = b""
    filename: str = "document.txt"
    mime_type: str = "text/plain"

    if "application/json" in content_type:
        body = await request.json()
        filename = body.get("filename", "document.txt")
        mime_type = body.get("mime_type", "text/plain")
        if body.get("content_text"):
            content_bytes = body["content_text"].encode("utf-8")
        elif body.get("content_base64"):
            import base64
            content_bytes = base64.b64decode(body["content_base64"])
        else:
            raise HTTPException(status_code=400, detail="Missing 'content_text' or 'content_base64' in JSON body.")
    elif "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        if not uploaded_file:
            raise HTTPException(status_code=400, detail="Missing file in multipart form data.")
        filename = getattr(uploaded_file, "filename", "upload.bin")
        content_bytes = await uploaded_file.read()
        mime_type = getattr(uploaded_file, "content_type", "application/octet-stream")
    else:
        content_bytes = await request.body()
        filename = request.headers.get("x-filename", "document.txt")
        mime_type = content_type or "text/plain"

    if not content_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    content_hash = hashlib.sha256(content_bytes).hexdigest()

    # Duplicate detection within the same Knowledge Base
    existing_doc = (
        db.query(DBKnowledgeDocument)
        .filter(
            DBKnowledgeDocument.knowledge_base_id == kb.id,
            DBKnowledgeDocument.content_hash == content_hash,
        )
        .first()
    )
    if existing_doc:
        return DocumentResponse(
            id=existing_doc.id,
            org_id=existing_doc.org_id,
            knowledge_base_id=existing_doc.knowledge_base_id,
            filename=existing_doc.filename,
            mime_type=existing_doc.mime_type,
            file_size=existing_doc.file_size,
            content_hash=existing_doc.content_hash,
            status=existing_doc.status,
            chunk_count=existing_doc.chunk_count,
            error_message=existing_doc.error_message,
            created_at=existing_doc.created_at.isoformat() if existing_doc.created_at else "",
            updated_at=existing_doc.updated_at.isoformat() if existing_doc.updated_at else "",
        )

    doc = DBKnowledgeDocument(
        id=f"doc_{uuid.uuid4().hex[:12]}",
        org_id=kb.org_id,
        knowledge_base_id=kb.id,
        filename=filename,
        mime_type=mime_type,
        file_size=len(content_bytes),
        content_hash=content_hash,
        status=DocumentStatus.PENDING.value,
        chunk_count=0,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Process and index
    _ingestion_pipeline.process_and_index(kb=kb, doc=doc, content=content_bytes, db=db)
    db.refresh(doc)

    return DocumentResponse(
        id=doc.id,
        org_id=doc.org_id,
        knowledge_base_id=doc.knowledge_base_id,
        filename=doc.filename,
        mime_type=doc.mime_type,
        file_size=doc.file_size,
        content_hash=doc.content_hash,
        status=doc.status,
        chunk_count=doc.chunk_count,
        error_message=doc.error_message,
        created_at=doc.created_at.isoformat() if doc.created_at else "",
        updated_at=doc.updated_at.isoformat() if doc.updated_at else "",
    )


@router.get("/{kb_id}/documents", response_model=List[DocumentResponse])
def list_documents(
    kb_id: str,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[DocumentResponse]:
    """List all documents in a Knowledge Base. Requires VIEWER role or higher."""
    kb = db.query(DBKnowledgeBase).filter(DBKnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found.")

    verify_org_access(db, current_user.id, kb.org_id, min_role=OrgRole.VIEWER)

    docs = db.query(DBKnowledgeDocument).filter(DBKnowledgeDocument.knowledge_base_id == kb.id).all()
    return [
        DocumentResponse(
            id=d.id,
            org_id=d.org_id,
            knowledge_base_id=d.knowledge_base_id,
            filename=d.filename,
            mime_type=d.mime_type,
            file_size=d.file_size,
            content_hash=d.content_hash,
            status=d.status,
            chunk_count=d.chunk_count,
            error_message=d.error_message,
            created_at=d.created_at.isoformat() if d.created_at else "",
            updated_at=d.updated_at.isoformat() if d.updated_at else "",
        )
        for d in docs
    ]


@router.get("/{kb_id}/documents/{doc_id}", response_model=DocumentResponse)
def get_document(
    kb_id: str,
    doc_id: str,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    """Get document details. Enforces organization tenant isolation."""
    kb = db.query(DBKnowledgeBase).filter(DBKnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found.")

    verify_org_access(db, current_user.id, kb.org_id, min_role=OrgRole.VIEWER)

    doc = (
        db.query(DBKnowledgeDocument)
        .filter(DBKnowledgeDocument.id == doc_id, DBKnowledgeDocument.knowledge_base_id == kb.id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    return DocumentResponse(
        id=doc.id,
        org_id=doc.org_id,
        knowledge_base_id=doc.knowledge_base_id,
        filename=doc.filename,
        mime_type=doc.mime_type,
        file_size=doc.file_size,
        content_hash=doc.content_hash,
        status=doc.status,
        chunk_count=doc.chunk_count,
        error_message=doc.error_message,
        created_at=doc.created_at.isoformat() if doc.created_at else "",
        updated_at=doc.updated_at.isoformat() if doc.updated_at else "",
    )


@router.delete("/{kb_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    kb_id: str,
    doc_id: str,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a document and remove its chunks from the customer's vector database. Requires MEMBER role or higher."""
    kb = db.query(DBKnowledgeBase).filter(DBKnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found.")

    verify_org_access(db, current_user.id, kb.org_id, min_role=OrgRole.MEMBER)

    doc = (
        db.query(DBKnowledgeDocument)
        .filter(DBKnowledgeDocument.id == doc_id, DBKnowledgeDocument.knowledge_base_id == kb.id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    _ingestion_pipeline.delete_document_index(kb, doc, db)
    db.delete(doc)
    kb.document_count = (
        db.query(DBKnowledgeDocument)
        .filter(
            DBKnowledgeDocument.knowledge_base_id == kb.id,
            DBKnowledgeDocument.id != doc.id,
            DBKnowledgeDocument.status == DocumentStatus.INDEXED.value,
        )
        .count()
    )
    db.commit()


@router.post("/{kb_id}/documents/{doc_id}/reindex", response_model=DocumentResponse)
def reindex_document(
    kb_id: str,
    doc_id: str,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    """Reindex an existing document from local storage."""
    kb = db.query(DBKnowledgeBase).filter(DBKnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found.")

    verify_org_access(db, current_user.id, kb.org_id, min_role=OrgRole.MEMBER)

    doc = (
        db.query(DBKnowledgeDocument)
        .filter(DBKnowledgeDocument.id == doc_id, DBKnowledgeDocument.knowledge_base_id == kb.id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    if not doc.storage_path or not os.path.exists(doc.storage_path):
        raise HTTPException(status_code=400, detail="Document storage file not found for re-indexing.")

    content = Path(doc.storage_path).read_bytes()
    _ingestion_pipeline.process_and_index(kb=kb, doc=doc, content=content, db=db)
    db.refresh(doc)

    return DocumentResponse(
        id=doc.id,
        org_id=doc.org_id,
        knowledge_base_id=doc.knowledge_base_id,
        filename=doc.filename,
        mime_type=doc.mime_type,
        file_size=doc.file_size,
        content_hash=doc.content_hash,
        status=doc.status,
        chunk_count=doc.chunk_count,
        error_message=doc.error_message,
        created_at=doc.created_at.isoformat() if doc.created_at else "",
        updated_at=doc.updated_at.isoformat() if doc.updated_at else "",
    )


# ---------------------------------------------------------------------------
# Retrieval Query Endpoint
# ---------------------------------------------------------------------------

@router.post("/{kb_id}/retrieve")
def test_retrieval(
    kb_id: str,
    req: RetrieveRequest,
    current_user: UserOrm = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Execute a retrieval query against the customer's database and return structured evidence trace."""
    kb = db.query(DBKnowledgeBase).filter(DBKnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge Base not found.")

    verify_org_access(db, current_user.id, kb.org_id, min_role=OrgRole.VIEWER)

    trace = _retrieval_service.retrieve(
        kb=kb,
        query=req.query,
        org_id=kb.org_id,
        retrieval_mode=req.retrieval_mode,
        top_k=req.top_k,
        filter_metadata=req.filter_metadata,
        max_graph_depth=req.max_graph_depth,
    )
    return trace.model_dump()

