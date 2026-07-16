"""
Selections API – create, browse, and delete version-pinned node selections.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.services.selection_service import SelectionService
from app.schemas.schemas import SelectionCreate, SelectionResponse
from loguru import logger

router = APIRouter(prefix="/selections", tags=["Selections"])


@router.post(
    "",
    response_model=SelectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new selection",
)
async def create_selection(
    payload: SelectionCreate, db: AsyncSession = Depends(get_db)
):
    """
    Creates a new version-pinned selection referencing the given node IDs.
    All nodes must belong to the specified version.
    """
    logger.info(
        f"POST /selections  name='{payload.name}' version={payload.version_id} "
        f"nodes={payload.node_ids}"
    )
    try:
        selection = await SelectionService.create_selection(
            db, payload.name, payload.version_id, payload.node_ids
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return selection


@router.get("", response_model=List[SelectionResponse], summary="List all selections")
async def list_selections(db: AsyncSession = Depends(get_db)):
    return await SelectionService.list_selections(db)


@router.get(
    "/{selection_id}",
    response_model=SelectionResponse,
    summary="Get a selection by ID",
)
async def get_selection(selection_id: str, db: AsyncSession = Depends(get_db)):
    selection = await SelectionService.get_selection(db, selection_id)
    if not selection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Selection not found.")
    return selection


@router.delete(
    "/{selection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a selection",
)
async def delete_selection(selection_id: str, db: AsyncSession = Depends(get_db)):
    deleted = await SelectionService.delete_selection(db, selection_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Selection not found.")
