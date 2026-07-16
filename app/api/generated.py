"""
Generated test cases API – trigger generation and retrieve with staleness info.
"""
from typing import Any, Dict, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from motor.motor_asyncio import AsyncIOMotorCollection

from app.database.session import get_db
from app.database.mongo import mongo_manager
from app.services.generation_service import GenerationService
from app.schemas.schemas import GenerationTrigger, TestCase, StalenessInfo
from loguru import logger


router = APIRouter(prefix="/generated", tags=["Generated Test Cases"])


def _get_collection() -> AsyncIOMotorCollection:
    if mongo_manager.collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB is not connected.",
        )
    return mongo_manager.collection


def _format_gen(gen: Dict[str, Any]) -> Dict[str, Any]:
    """Serialise dates and structure the response payload."""
    # Convert datetime objects to ISO strings for JSON serialisation
    for key in ("generated_at", "stale_checked_at"):
        val = gen.get(key)
        if isinstance(val, datetime):
            gen[key] = val.isoformat()
    return gen


# ── Trigger generation ────────────────────────────────────────────────── #

@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Generate QA test cases for a selection",
)
async def generate_test_cases(
    payload: GenerationTrigger,
    db: AsyncSession = Depends(get_db),
    collection: AsyncIOMotorCollection = Depends(_get_collection),
):
    """
    Reconstructs the selection text, calls Groq LLM, validates with Pydantic,
    and stores the result in MongoDB.  Returns the full generation record
    (including status CURRENT / FAILED).
    """
    logger.info(f"POST /generated  selection_id={payload.selection_id}")
    try:
        result = await GenerationService.generate(db, collection, payload.selection_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return _format_gen(result)


# ── List all generations ──────────────────────────────────────────────── #

@router.get("", summary="List all generations with staleness info")
async def list_generated(
    db: AsyncSession = Depends(get_db),
    collection: AsyncIOMotorCollection = Depends(_get_collection),
):
    gens = await GenerationService.list_all(db, collection)
    return [_format_gen(g) for g in gens]


# ── Retrieve by selection_id ──────────────────────────────────────────── #

@router.get(
    "/{selection_id}",
    summary="Get the latest generation for a selection (with staleness check)",
)
async def get_generated(
    selection_id: str,
    db: AsyncSession = Depends(get_db),
    collection: AsyncIOMotorCollection = Depends(_get_collection),
):
    """
    Returns the most recent generation record for a selection.
    Performs a live staleness check and updates the status if needed.
    """
    gen = await GenerationService.get_with_staleness(db, collection, selection_id)
    if not gen:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No generation found for selection {selection_id}.",
        )
    return _format_gen(gen)


# ── Retrieve by node_id ───────────────────────────────────────────────── #

@router.get(
    "/node/{node_id}",
    summary="Get all generations that reference a specific node",
)
async def get_generated_by_node(
    node_id: str,
    db: AsyncSession = Depends(get_db),
    collection: AsyncIOMotorCollection = Depends(_get_collection),
):
    gens = await GenerationService.get_by_node_id(db, collection, node_id)
    if not gens:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No generations found referencing node {node_id}.",
        )
    return [_format_gen(g) for g in gens]
