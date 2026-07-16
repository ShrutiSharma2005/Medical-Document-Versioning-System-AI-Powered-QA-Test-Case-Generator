"""
Nodes API – retrieve individual nodes and their children.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.repositories.document_repo import DocumentRepository
from app.schemas.schemas import NodeResponse
from loguru import logger

router = APIRouter(prefix="/nodes", tags=["Nodes"])


@router.get("/{node_id}", response_model=NodeResponse, summary="Get node by ID")
async def get_node(node_id: str, db: AsyncSession = Depends(get_db)):
    """Returns a single node record by its UUID."""
    repo = DocumentRepository(db)
    node = await repo.get_node(node_id)
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")
    return node


@router.get(
    "/{node_id}/children",
    response_model=List[NodeResponse],
    summary="Get direct children of a node",
)
async def get_node_children(node_id: str, db: AsyncSession = Depends(get_db)):
    """Returns the immediate child nodes of a given node, ordered by sort_order."""
    repo = DocumentRepository(db)
    # Verify parent exists first
    parent = await repo.get_node(node_id)
    if not parent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")
    children = await repo.get_node_children(node_id)
    return children
