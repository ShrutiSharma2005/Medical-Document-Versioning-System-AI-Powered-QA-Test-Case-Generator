"""
Tests for Selection service and text reconstruction.
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.document_service import DocumentService
from app.services.selection_service import SelectionService, reconstruct_selection_text
from app.repositories.document_repo import DocumentRepository

MARKDOWN = """\
# Device Overview

The CT-200 monitors blood pressure.

## Intended Use

For adults 22–42 cm arm circumference.

## Contraindications

Not for neonates.
"""


@pytest.mark.asyncio
class TestSelectionService:
    async def _setup(self, db):
        """Helper to create a document + version and return node IDs."""
        result = await DocumentService.upload_document(db, "CT-200 sel", MARKDOWN)
        repo = DocumentRepository(db)
        nodes = await repo.get_nodes_by_version(result["version_id"])
        return result["version_id"], nodes

    async def test_create_selection_succeeds(self, db: AsyncSession):
        version_id, nodes = await self._setup(db)
        sel = await SelectionService.create_selection(
            db, "My Selection", version_id, [nodes[0].id, nodes[1].id]
        )
        assert sel.id
        assert sel.name == "My Selection"
        assert sel.version_id == version_id
        assert len(sel.nodes) == 2

    async def test_selection_is_version_pinned(self, db: AsyncSession):
        version_id, nodes = await self._setup(db)
        sel = await SelectionService.create_selection(
            db, "Pinned", version_id, [nodes[0].id]
        )
        assert sel.version_id == version_id

    async def test_create_selection_with_wrong_version_raises(self, db: AsyncSession):
        version_id, nodes = await self._setup(db)
        with pytest.raises(ValueError, match="does not exist"):
            await SelectionService.create_selection(
                db, "Bad", "wrong-version-id", [nodes[0].id]
            )

    async def test_get_selection_returns_selection(self, db: AsyncSession):
        version_id, nodes = await self._setup(db)
        created = await SelectionService.create_selection(
            db, "Get Test", version_id, [nodes[0].id]
        )
        fetched = await SelectionService.get_selection(db, created.id)
        assert fetched is not None
        assert fetched.id == created.id

    async def test_list_selections_contains_created(self, db: AsyncSession):
        version_id, nodes = await self._setup(db)
        await SelectionService.create_selection(db, "Listed", version_id, [nodes[0].id])
        sels = await SelectionService.list_selections(db)
        names = [s.name for s in sels]
        assert "Listed" in names

    async def test_delete_selection(self, db: AsyncSession):
        version_id, nodes = await self._setup(db)
        sel = await SelectionService.create_selection(
            db, "To Delete", version_id, [nodes[0].id]
        )
        deleted = await SelectionService.delete_selection(db, sel.id)
        assert deleted is True
        fetched = await SelectionService.get_selection(db, sel.id)
        assert fetched is None

    async def test_delete_nonexistent_selection_returns_false(self, db: AsyncSession):
        result = await SelectionService.delete_selection(db, "non-existent-id")
        assert result is False


class TestReconstructSelectionText:
    def _make_stub_nodes(self):
        """Create mock node-like objects with sort_order, heading, level, text."""
        from dataclasses import dataclass

        @dataclass
        class NodeStub:
            id: str
            sort_order: int
            heading: str
            level: int
            text: str

        return [
            NodeStub("n1", 0, "Device Overview", 1, "Body text 1."),
            NodeStub("n2", 1, "Intended Use", 2, "Body text 2."),
            NodeStub("n3", 2, "", 5, "Orphan paragraph."),
        ]

    def test_heading_prefixes_level_hashes(self):
        nodes = self._make_stub_nodes()
        text = reconstruct_selection_text(nodes)
        assert "# Device Overview" in text
        assert "## Intended Use" in text

    def test_empty_heading_not_prefixed(self):
        nodes = self._make_stub_nodes()
        text = reconstruct_selection_text(nodes)
        assert "Orphan paragraph." in text
        # Empty heading node should NOT produce "#####\nOrphan paragraph."
        assert "##### " not in text

    def test_body_text_preserved(self):
        nodes = self._make_stub_nodes()
        text = reconstruct_selection_text(nodes)
        assert "Body text 1." in text
        assert "Body text 2." in text

    def test_order_respects_sort_order(self):
        nodes = self._make_stub_nodes()
        text = reconstruct_selection_text(nodes)
        idx1 = text.index("Device Overview")
        idx2 = text.index("Intended Use")
        assert idx1 < idx2
