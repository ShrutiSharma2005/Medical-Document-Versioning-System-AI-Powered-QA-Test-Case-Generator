"""
Search API – full-text search across node headings and body text.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.repositories.document_repo import DocumentRepository
from app.schemas.schemas import SearchResult
from loguru import logger

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("", response_model=List[SearchResult], summary="Search nodes by keyword")
async def search_nodes(
    query: str = Query(..., min_length=1, description="Keyword to search for"),
    document_id: Optional[str] = Query(None, description="Restrict search to a specific document"),
    db: AsyncSession = Depends(get_db),
):
    """
    Searches all nodes for the given keyword in both headings and body text.
    Returns a ranked list of matches with a short snippet.
    Optionally filter results to a specific document.
    """
    logger.info(f"GET /search?query='{query}' document_id={document_id}")
    repo = DocumentRepository(db)
    nodes = await repo.search_nodes(query, document_id=document_id)

    results: List[SearchResult] = []
    q_lower = query.lower()

    for node in nodes:
        # Determine match type and build snippet
        heading_hit = q_lower in node.heading.lower()
        body_hit = q_lower in node.text.lower()
        match_type = "heading" if heading_hit else "body"

        # Build a short snippet (up to 200 chars) centred on the query match in body text
        if body_hit:
            idx = node.text.lower().find(q_lower)
            start = max(0, idx - 80)
            end = min(len(node.text), idx + len(query) + 80)
            snippet = ("..." if start > 0 else "") + node.text[start:end] + ("..." if end < len(node.text) else "")
        else:
            snippet = node.heading

        results.append(
            SearchResult(
                node_id=node.id,
                version_id=node.version_id,
                heading=node.heading,
                level=node.level,
                snippet=snippet,
                match_type=match_type,
            )
        )

    return results
