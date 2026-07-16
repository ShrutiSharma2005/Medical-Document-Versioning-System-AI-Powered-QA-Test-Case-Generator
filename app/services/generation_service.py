"""
Generation service: build context text, call Groq, persist to MongoDB,
and check staleness on retrieval.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.repositories.document_repo import DocumentRepository
from app.repositories.generation_repo import GenerationRepository
from app.services.selection_service import SelectionService, reconstruct_selection_text
from app.llm.groq_client import generate_test_cases
from app.schemas.schemas import StalenessInfo
from app.models.document import NodeMapping
from sqlalchemy.future import select


class GenerationService:
    """Handles LLM test-case generation and staleness-aware retrieval."""

    # ------------------------------------------------------------------ #
    #  Generate test cases for a selection
    # ------------------------------------------------------------------ #
    @staticmethod
    async def generate(
        db: AsyncSession,
        collection,
        selection_id: str,
    ) -> Dict[str, Any]:
        """
        1. Loads the selection and reconstructs text.
        2. Calls Groq with retry logic.
        3. Persists the result to MongoDB.
        4. Returns the full generation record.
        """
        repo = DocumentRepository(db)
        gen_repo = GenerationRepository(collection)

        # Load selection + nodes
        selection = await SelectionService.get_selection(db, selection_id)
        if not selection:
            raise ValueError(f"Selection {selection_id} not found.")

        nodes = sorted(selection.nodes, key=lambda n: n.sort_order)
        selection_text = reconstruct_selection_text(nodes)
        logger.info(
            f"Generating test cases for selection '{selection.name}' "
            f"({len(nodes)} nodes, {len(selection_text)} chars)."
        )

        # Snapshot hashes at generation time
        node_hashes = {n.id: n.content_hash for n in nodes}

        # Build initial Mongo record (will be updated after LLM call)
        record: Dict[str, Any] = {
            "selection_id": selection_id,
            "version_id": selection.version_id,
            "prompt": selection_text,
            "raw_response": None,
            "parsed_testcases": [],
            "node_hashes": node_hashes,
            "generated_at": datetime.now(timezone.utc),
            "status": "CURRENT",
            "stale_reason": None,
            "llm_model": None,
            "response_time": None,
        }

        try:
            parsed, raw, model_used, response_time = await generate_test_cases(selection_text)
            record.update(
                {
                    "raw_response": raw,
                    "parsed_testcases": [tc.model_dump() for tc in parsed.test_cases],
                    "llm_model": model_used,
                    "response_time": response_time,
                    "status": "CURRENT",
                }
            )
            logger.info(
                f"Generation succeeded: {len(parsed.test_cases)} test cases, "
                f"model={model_used}, time={response_time:.2f}s."
            )
        except RuntimeError as exc:
            # Parsing failed after retry — store raw response in FAILED state
            raw_fallback = str(exc)
            record.update(
                {
                    "raw_response": raw_fallback,
                    "status": "FAILED",
                    "stale_reason": str(exc),
                }
            )
            logger.error(f"Generation FAILED for selection {selection_id}: {exc}")

        record_id = await gen_repo.insert(record)
        record["id"] = record_id
        return record

    # ------------------------------------------------------------------ #
    #  Retrieve generation with live staleness check
    # ------------------------------------------------------------------ #
    @staticmethod
    async def get_with_staleness(
        db: AsyncSession,
        collection,
        selection_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves the latest generation for a selection and injects a live
        staleness check by comparing stored node_hashes against the current
        SQLite node records.
        """
        gen_repo = GenerationRepository(collection)
        doc_repo = DocumentRepository(db)

        gen = await gen_repo.get_by_selection_id(selection_id)
        if not gen:
            return None

        staleness_info = await GenerationService._compute_staleness(
            db, doc_repo, gen_repo, gen
        )
        gen["staleness_info"] = staleness_info.model_dump()
        return gen

    @staticmethod
    async def get_by_node_id(
        db: AsyncSession,
        collection,
        node_id: str,
    ) -> List[Dict[str, Any]]:
        gen_repo = GenerationRepository(collection)
        doc_repo = DocumentRepository(db)

        gens = await gen_repo.list_by_node_id(node_id)
        for gen in gens:
            staleness_info = await GenerationService._compute_staleness(
                db, doc_repo, gen_repo, gen
            )
            gen["staleness_info"] = staleness_info.model_dump()
        return gens

    @staticmethod
    async def list_all(
        db: AsyncSession,
        collection,
    ) -> List[Dict[str, Any]]:
        gen_repo = GenerationRepository(collection)
        doc_repo = DocumentRepository(db)

        gens = await gen_repo.list_all()
        for gen in gens:
            staleness_info = await GenerationService._compute_staleness(
                db, doc_repo, gen_repo, gen
            )
            gen["staleness_info"] = staleness_info.model_dump()
        return gens

    # ------------------------------------------------------------------ #
    #  Internal staleness check
    # ------------------------------------------------------------------ #
    @staticmethod
    async def _compute_staleness(
        db: AsyncSession,
        doc_repo: DocumentRepository,
        gen_repo: GenerationRepository,
        gen: Dict[str, Any],
    ) -> StalenessInfo:
        """
        Compares the stored node_hashes against the current SQLite node records.
        If any node has been modified (hash change) or deleted, marks as STALE.
        """
        node_hashes: Dict[str, str] = gen.get("node_hashes", {})
        if not node_hashes:
            return StalenessInfo(is_stale=False)

        changed_headings: List[str] = []
        diff_summaries: List[str] = []

        for node_id, stored_hash in node_hashes.items():
            # Check if node still exists
            node = await doc_repo.get_node(node_id)
            if node is None:
                changed_headings.append(f"[DELETED] node_id={node_id}")
                diff_summaries.append(f"Node {node_id} was deleted from the document.")
                continue

            # Check for hash change (modification)
            if node.content_hash != stored_hash:
                changed_headings.append(f"[MODIFIED] '{node.heading}'")
                diff_summaries.append(
                    f"Section '{node.heading}' content changed "
                    f"(prev_hash={stored_hash[:8]}..., "
                    f"curr_hash={node.content_hash[:8]}...)."
                )

        if changed_headings:
            stale_reason = (
                "The following sections changed since generation: "
                + ", ".join(changed_headings)
            )
            # Persist updated status so future reads are fast
            await gen_repo.update_status(
                gen["selection_id"], "STALE", stale_reason
            )
            return StalenessInfo(
                is_stale=True,
                stale_reason=stale_reason,
                changed_headings=changed_headings,
                diff_summaries=diff_summaries,
            )

        # All hashes match → CURRENT
        if gen.get("status") == "STALE":
            # Edge case: was previously stale but content restored
            await gen_repo.update_status(gen["selection_id"], "CURRENT", None)

        return StalenessInfo(is_stale=False)
