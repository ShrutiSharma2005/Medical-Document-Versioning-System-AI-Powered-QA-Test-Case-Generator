"""
Tests for MongoDB storage and staleness detection.
Uses unittest.mock to mock MongoDB collection behavior.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.generation_service import GenerationService
from app.services.document_service import DocumentService
from app.repositories.document_repo import DocumentRepository
from app.repositories.generation_repo import GenerationRepository

MARKDOWN_V1 = """\
# Section 1

Content of section 1.

# Section 2

Content of section 2.
"""

MARKDOWN_V2 = """\
# Section 1

Content of section 1.

# Section 2

Content of section 2 has been updated.
"""


@pytest.mark.asyncio
class TestStalenessDetection:
    async def test_staleness_computation_current(self, db: AsyncSession):
        """If node hashes match current database nodes, status remains CURRENT."""
        # 1. Ingest V1
        upload = await DocumentService.upload_document(db, "Staleness Doc", MARKDOWN_V1)
        doc_repo = DocumentRepository(db)
        nodes = await doc_repo.get_nodes_by_version(upload["version_id"])
        
        # 2. Mock generation record
        gen_record = {
            "selection_id": "sel-123",
            "version_id": upload["version_id"],
            "node_hashes": {n.id: n.content_hash for n in nodes},
            "status": "CURRENT",
            "stale_reason": None
        }
        
        # 3. Compute staleness
        mock_gen_repo = MagicMock()
        mock_gen_repo.update_status = AsyncMock()
        
        staleness = await GenerationService._compute_staleness(db, doc_repo, mock_gen_repo, gen_record)
        assert staleness.is_stale is False
        assert len(staleness.changed_headings) == 0

    async def test_staleness_computation_modified(self, db: AsyncSession):
        """If a node's hash changes in SQLite, staleness computation marks it as STALE."""
        # 1. Ingest V1
        upload = await DocumentService.upload_document(db, "Staleness Doc", MARKDOWN_V1)
        doc_repo = DocumentRepository(db)
        nodes = await doc_repo.get_nodes_by_version(upload["version_id"])
        
        # 2. Mock generation record with one altered hash (simulating database update or drift)
        node_hashes = {n.id: n.content_hash for n in nodes}
        altered_node_id = nodes[0].id
        node_hashes[altered_node_id] = "altered_hash_12345"
        
        gen_record = {
            "selection_id": "sel-123",
            "version_id": upload["version_id"],
            "node_hashes": node_hashes,
            "status": "CURRENT",
            "stale_reason": None
        }
        
        # 3. Compute staleness
        mock_gen_repo = MagicMock()
        mock_gen_repo.update_status = AsyncMock()
        
        staleness = await GenerationService._compute_staleness(db, doc_repo, mock_gen_repo, gen_record)
        assert staleness.is_stale is True
        assert len(staleness.changed_headings) == 1
        assert "MODIFIED" in staleness.changed_headings[0]
        mock_gen_repo.update_status.assert_called_once()

    async def test_staleness_computation_deleted(self, db: AsyncSession):
        """If a referenced node no longer exists in SQLite, staleness computation marks it as STALE."""
        # 1. Ingest V1
        upload = await DocumentService.upload_document(db, "Staleness Doc", MARKDOWN_V1)
        doc_repo = DocumentRepository(db)
        
        # 2. Mock generation record referencing a deleted node UUID
        gen_record = {
            "selection_id": "sel-123",
            "version_id": upload["version_id"],
            "node_hashes": {"non-existent-node-uuid": "hash123"},
            "status": "CURRENT",
            "stale_reason": None
        }
        
        mock_gen_repo = MagicMock()
        mock_gen_repo.update_status = AsyncMock()
        
        staleness = await GenerationService._compute_staleness(db, doc_repo, mock_gen_repo, gen_record)
        assert staleness.is_stale is True
        assert "DELETED" in staleness.changed_headings[0]

    async def test_reingest_propagates_staleness_to_mongo(self, db: AsyncSession):
        """Uploading V2 automatically checks V1 generations and marks them stale in Mongo."""
        # 1. Upload V1
        v1_upload = await DocumentService.upload_document(db, "Drift Manual", MARKDOWN_V1)
        doc_repo = DocumentRepository(db)
        v1_nodes = await doc_repo.get_nodes_by_version(v1_upload["version_id"])
        
        # 2. Prepare mock mongo generation pinned to V1
        mock_col = MagicMock()
        mock_col.update_many = AsyncMock(return_value=MagicMock(modified_count=1))
        gen_repo = GenerationRepository(mock_col)
        
        # Simulated generation linked to V1 (referencing Section 2)
        node_hashes = {n.id: n.content_hash for n in v1_nodes}
        mock_generation_record = {
            "_id": "65f8a2f8c85c2c525f000001",
            "selection_id": "sel-777",
            "version_id": v1_upload["version_id"],
            "node_hashes": node_hashes,
            "status": "CURRENT",
            "stale_reason": None,
            "generated_at": datetime.now(timezone.utc)
        }
        
        # Mock cursor find execution for list_all
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[mock_generation_record])
        mock_col.find.return_value = mock_cursor
        
        # 3. Perform Re-ingestion (V2) where Section 2 changed
        with patch("app.database.mongo.mongo_manager.collection", mock_col):
            reingest_res = await DocumentService.reingest_document(
                db, v1_upload["document_id"], MARKDOWN_V2
            )
            
            # The test should report that V1 generations were marked as STALE
            assert reingest_res["stale_generations_marked"] == 1
            # Verify update_many was triggered on the collection
            mock_col.update_many.assert_called_once()
            args, kwargs = mock_col.update_many.call_args
            assert args[0]["selection_id"] == "sel-777"
            assert args[1]["$set"]["status"] == "STALE"
            assert "changed" in args[1]["$set"]["stale_reason"].lower()
