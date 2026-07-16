"""
Core document ingestion service: parse → persist → compare → detect staleness.
"""
import uuid
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.parser.markdown_parser import parse_markdown_to_nodes
from app.repositories.document_repo import DocumentRepository
from app.repositories.generation_repo import GenerationRepository
from app.versioning.matching import compare_versions
from app.database.mongo import mongo_manager
from app.models.document import Node


class DocumentService:
    """
    Orchestrates document upload, re-ingestion, and version comparison.
    All methods are async and receive a SQLAlchemy AsyncSession.
    """

    # ------------------------------------------------------------------ #
    #  Upload Version 1 (new document)
    # ------------------------------------------------------------------ #
    @staticmethod
    async def upload_document(
        db: AsyncSession, title: str, markdown_content: str
    ) -> Dict[str, Any]:
        """
        Parses markdown, creates a new Document + DocumentVersion 1, and persists
        all nodes to SQLite.

        Returns a summary dict with document_id, version_id, node_count.
        """
        logger.info(f"Starting document upload: '{title}'")
        repo = DocumentRepository(db)

        # 1. Create top-level Document record
        document = await repo.create_document(title)

        # 2. Create Version 1
        version = await repo.create_version(document.id, version_num=1)

        # 3. Parse markdown into node dicts
        node_dicts = parse_markdown_to_nodes(markdown_content, version.id)

        # 4. Persist nodes
        await repo.create_nodes_bulk(node_dicts)
        await db.commit()

        logger.info(
            f"Document '{title}' (id={document.id}) uploaded. "
            f"Version 1 (id={version.id}) with {len(node_dicts)} nodes persisted."
        )
        return {
            "document_id": document.id,
            "version_id": version.id,
            "node_count": len(node_dicts),
        }

    # ------------------------------------------------------------------ #
    #  Re-ingest Version 2 (new version for existing document)
    # ------------------------------------------------------------------ #
    @staticmethod
    async def reingest_document(
        db: AsyncSession, document_id: str, markdown_content: str
    ) -> Dict[str, Any]:
        """
        Parses markdown into a new DocumentVersion (N+1) for an existing document,
        runs the hybrid version comparison, persists mappings, and marks stale
        MongoDB generation records.

        Returns a summary dict with version_id, comparison summary, and stale count.
        """
        logger.info(f"Re-ingesting document id={document_id}...")
        repo = DocumentRepository(db)

        # 1. Verify document exists
        document = await repo.get_document(document_id)
        if not document:
            raise ValueError(f"Document {document_id} not found.")

        # 2. Identify the latest version (base for comparison)
        prev_version = await repo.get_latest_version(document_id)
        if not prev_version:
            raise ValueError(f"No existing version found for document {document_id}.")
        prev_version_num = prev_version.version_num

        # 3. Create new version
        new_version = await repo.create_version(document_id, prev_version_num + 1)

        # 4. Parse markdown
        node_dicts = parse_markdown_to_nodes(markdown_content, new_version.id)

        # 5. Persist new nodes
        new_nodes = await repo.create_nodes_bulk(node_dicts)

        # 6. Load previous-version nodes for comparison
        prev_nodes: List[Node] = await repo.get_nodes_by_version(prev_version.id)

        # 7. Hybrid comparison
        mappings, summary = compare_versions(prev_nodes, new_nodes)

        # Enrich added nodes list for the diff_data JSON
        v2_ids_in_mappings = {m["to_node_id"] for m in mappings if m["to_node_id"]}
        added_nodes = [
            {"id": n.id, "heading": n.heading, "level": n.level}
            for n in new_nodes
            if n.id not in v2_ids_in_mappings
        ]
        diff_data = {
            **summary,
            "added_nodes": added_nodes,
        }

        # 8. Persist comparison and node mappings
        await repo.save_version_comparison(
            from_version_id=prev_version.id,
            to_version_id=new_version.id,
            diff_data=diff_data,
            node_mappings=mappings,
        )
        await db.commit()

        # 9. Staleness detection: mark affected MongoDB records
        stale_count = await DocumentService._mark_stale_generations(
            db, repo, prev_version.id, mappings, new_version.id
        )

        logger.info(
            f"Re-ingestion complete. New version={new_version.version_num} "
            f"(id={new_version.id}). {stale_count} generation(s) marked STALE."
        )
        return {
            "document_id": document_id,
            "new_version_id": new_version.id,
            "new_version_num": new_version.version_num,
            "node_count": len(node_dicts),
            "comparison_summary": summary,
            "stale_generations_marked": stale_count,
        }

    # ------------------------------------------------------------------ #
    #  Staleness detection helper
    # ------------------------------------------------------------------ #
    @staticmethod
    async def _mark_stale_generations(
        db: AsyncSession,
        repo: DocumentRepository,
        prev_version_id: str,
        mappings: List[Dict[str, Any]],
        new_version_id: str,
    ) -> int:
        """
        Checks all MongoDB generation records whose version_id matches prev_version_id.
        For any record where a referenced node has been modified or deleted, updates
        its status to STALE with an appropriate reason.

        Returns the total number of MongoDB records updated.
        """
        if mongo_manager.collection is None:
            logger.warning("MongoDB not connected; skipping staleness propagation.")
            return 0

        gen_repo = GenerationRepository(mongo_manager.collection)

        # Build a quick lookup: from_node_id → {status, diff}
        mapping_by_node: Dict[str, Dict[str, Any]] = {
            m["from_node_id"]: m for m in mappings if m["from_node_id"]
        }

        # All generation records pinned to the previous version
        all_gens = await gen_repo.list_all()
        prev_gens = [g for g in all_gens if g.get("version_id") == prev_version_id]

        stale_count = 0
        for gen in prev_gens:
            node_hashes: Dict[str, str] = gen.get("node_hashes", {})
            stale_nodes: List[str] = []

            for node_id in node_hashes:
                mapping = mapping_by_node.get(node_id)
                if mapping and mapping["comparison_status"] in ("modified", "deleted"):
                    # Fetch heading for readable stale_reason
                    node = await repo.get_node(node_id)
                    heading = node.heading if node else node_id
                    stale_nodes.append(heading)

            if stale_nodes:
                stale_reason = (
                    f"The following sections changed in the new version: "
                    + ", ".join(f"'{h}'" for h in stale_nodes)
                )
                await gen_repo.update_status(
                    gen["selection_id"], "STALE", stale_reason
                )
                stale_count += 1

        return stale_count
