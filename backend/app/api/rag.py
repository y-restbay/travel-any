import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.admin_auth import require_admin
from app.db.session import get_db
from app.rag import get_rag_pipeline
from app.rag.schemas import IngestResult, RAGDebugResult, RetrieveRequest, RetrieveResult, TextIngestRequest
from app.services.config_service import get_active_llm_config

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get("/stats")
def rag_stats(_: str = Depends(require_admin)) -> Dict[str, Any]:
    return get_rag_pipeline().stats()


@router.post("/rebuild-vector-index")
def rebuild_vector_index(_: str = Depends(require_admin)) -> Dict[str, Any]:
    return get_rag_pipeline().rebuild_vector_index()


@router.post("/ingest/text", response_model=IngestResult)
def ingest_text(payload: TextIngestRequest, _: str = Depends(require_admin)) -> IngestResult:
    metadata = {**payload.metadata}
    if payload.doc_type:
        metadata["doc_type"] = payload.doc_type
    if payload.source:
        metadata["source"] = payload.source
    return get_rag_pipeline().ingest_text(payload.text, payload.filename, metadata)


@router.post("/ingest/upload", response_model=IngestResult)
async def ingest_upload(
    file: UploadFile = File(...),
    doc_type: Optional[str] = Form(default=None),
    source: Optional[str] = Form(default=None),
    metadata_json: Optional[str] = Form(default=None),
    _: str = Depends(require_admin),
) -> IngestResult:
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Only UTF-8 text uploads are supported in V1") from exc

    metadata: Dict[str, Any] = {}
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="metadata_json must be valid JSON") from exc
    if doc_type:
        metadata["doc_type"] = doc_type
    if source:
        metadata["source"] = source

    return get_rag_pipeline().ingest_text(text, file.filename or "upload.txt", metadata)


@router.post("/retrieve", response_model=RetrieveResult)
def retrieve(payload: RetrieveRequest, db: Session = Depends(get_db)) -> RetrieveResult:
    return get_rag_pipeline().retrieve_context(payload.query, llm_config=get_active_llm_config(db), top_k=payload.top_k)


@router.post("/debug", response_model=RAGDebugResult)
def debug_retrieve(
    payload: RetrieveRequest,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RAGDebugResult:
    return get_rag_pipeline().debug_retrieve(payload.query, llm_config=get_active_llm_config(db), top_k=payload.top_k)
