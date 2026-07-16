"""
Versions API – browse document versions and their node trees.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.repositories.document_repo import DocumentRepository
from app.schemas.schemas import DocumentVersionDetail, DocumentVersionResponse
from loguru import logger

router = APIRouter(prefix="/versions", tags=["Versions"])


@router.get("", response_model=List[DocumentVersionResponse], summary="List all versions")
async def list_versions(db: AsyncSession = Depends(get_db)):
    """Returns all document versions across all documents, newest first."""
    repo = DocumentRepository(db)
    return await repo.list_versions()


@router.get(
    "/{version_id}",
    response_model=DocumentVersionDetail,
    summary="Get version details with nodes",
)
async def get_version(version_id: str, db: AsyncSession = Depends(get_db)):
    """Returns a specific version, including its full flat node list."""
    repo = DocumentRepository(db)
    ver = await repo.get_version(version_id)
    if not ver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    return ver
