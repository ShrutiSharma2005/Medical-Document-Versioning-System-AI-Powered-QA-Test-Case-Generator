"""
Document upload/reingest and browse API endpoints.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.services.document_service import DocumentService
from app.repositories.document_repo import DocumentRepository
from app.schemas.schemas import DocumentResponse, DocumentVersionDetail, NodeResponse
from loguru import logger

router = APIRouter(prefix="/documents", tags=["Documents"])


# ── Helpers ──────────────────────────────────────────────────────────────── #

async def _read_file(file: UploadFile) -> str:
    raw = await file.read()
    return raw.decode("utf-8", errors="replace")


# ── Upload Version 1 ─────────────────────────────────────────────────────── #

@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload Version 1 of a document",
)
async def upload_document(
    title: str = Form(...),
    file: UploadFile = File(..., description="Markdown file"),
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts a Markdown file and a document title.
    Parses it into a hierarchical node tree, creates Document + Version 1,
    and persists all nodes to SQLite.
    """
    logger.info(f"POST /documents/upload  title='{title}' filename='{file.filename}'")
    content = await _read_file(file)
    if not content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty.",
        )
    try:
        result = await DocumentService.upload_document(db, title, content)
    except Exception as exc:
        logger.exception("Document upload failed.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return result


# ── Re-ingest Version N+1 ─────────────────────────────────────────────────── #

@router.post(
    "/reingest",
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new version of an existing document",
)
async def reingest_document(
    document_id: str = Form(...),
    file: UploadFile = File(..., description="New version Markdown file"),
    db: AsyncSession = Depends(get_db),
):
    """
    Parses the uploaded Markdown as a new version of the given document.
    Runs version comparison (hybrid matching) and marks stale MongoDB generations.
    """
    logger.info(
        f"POST /documents/reingest  document_id='{document_id}' filename='{file.filename}'"
    )
    content = await _read_file(file)
    if not content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty.",
        )
    try:
        result = await DocumentService.reingest_document(db, document_id, content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        logger.exception("Document re-ingestion failed.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return result


# ── Browse ───────────────────────────────────────────────────────────────── #

@router.get("", response_model=List[DocumentResponse], summary="List all documents")
async def list_documents(db: AsyncSession = Depends(get_db)):
    repo = DocumentRepository(db)
    docs = await repo.list_documents()
    return docs


@router.get("/{document_id}", response_model=DocumentResponse, summary="Get document by ID")
async def get_document(document_id: str, db: AsyncSession = Depends(get_db)):
    repo = DocumentRepository(db)
    doc = await repo.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return doc
