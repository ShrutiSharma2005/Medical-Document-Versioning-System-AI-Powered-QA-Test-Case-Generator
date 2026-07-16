"""
Integration tests for the Document service – upload, re-ingest, search.
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.document_service import DocumentService
from app.repositories.document_repo import DocumentRepository

MARKDOWN_V1 = """\
# Device Overview

The CT-200 is an oscillometric blood pressure monitor.

## Intended Use

For adults with arm circumference 22–42 cm.

## Contraindications

Not for use on neonates.
"""

MARKDOWN_V2 = """\
# Device Overview

The CT-200 is an oscillometric blood pressure monitor. Updated description.

## Intended Use

For adults with arm circumference 22–42 cm and a new requirement.

## Contraindications

Not for use on neonates or infants.

## Data Export

Starting with firmware 1.4, CSV export is supported.
"""


@pytest.mark.asyncio
class TestDocumentService:
    async def test_upload_creates_document_and_version(self, db: AsyncSession):
        result = await DocumentService.upload_document(db, "CT-200 Manual", MARKDOWN_V1)
        assert result["document_id"]
        assert result["version_id"]
        assert result["node_count"] > 0

    async def test_upload_creates_v1_version_num(self, db: AsyncSession):
        result = await DocumentService.upload_document(db, "CT-200 Manual", MARKDOWN_V1)
        repo = DocumentRepository(db)
        version = await repo.get_version(result["version_id"])
        assert version.version_num == 1

    async def test_reingest_creates_new_version(self, db: AsyncSession):
        upload = await DocumentService.upload_document(db, "CT-200 v1", MARKDOWN_V1)
        reingest = await DocumentService.reingest_document(db, upload["document_id"], MARKDOWN_V2)
        assert reingest["new_version_num"] == 2

    async def test_reingest_comparison_detects_changes(self, db: AsyncSession):
        upload = await DocumentService.upload_document(db, "CT-200 comp", MARKDOWN_V1)
        reingest = await DocumentService.reingest_document(db, upload["document_id"], MARKDOWN_V2)
        summary = reingest["comparison_summary"]
        # At minimum some nodes must be modified or added
        assert summary["modified_count"] + summary["added_count"] > 0

    async def test_reingest_added_section_counted(self, db: AsyncSession):
        upload = await DocumentService.upload_document(db, "CT-200 add", MARKDOWN_V1)
        reingest = await DocumentService.reingest_document(db, upload["document_id"], MARKDOWN_V2)
        summary = reingest["comparison_summary"]
        # "Data Export" is new in V2
        assert summary["added_count"] >= 1

    async def test_reingest_raises_on_unknown_document(self, db: AsyncSession):
        with pytest.raises(ValueError, match="not found"):
            await DocumentService.reingest_document(db, "non-existent-id", MARKDOWN_V2)

    async def test_search_finds_heading(self, db: AsyncSession):
        await DocumentService.upload_document(db, "CT-200 search", MARKDOWN_V1)
        repo = DocumentRepository(db)
        results = await repo.search_nodes("Intended Use")
        assert any("Intended Use" in r.heading for r in results)

    async def test_search_finds_body_text(self, db: AsyncSession):
        await DocumentService.upload_document(db, "CT-200 body-search", MARKDOWN_V1)
        repo = DocumentRepository(db)
        results = await repo.search_nodes("oscillometric")
        assert len(results) > 0

    async def test_list_documents_includes_uploaded(self, db: AsyncSession):
        await DocumentService.upload_document(db, "CT-200 List", MARKDOWN_V1)
        repo = DocumentRepository(db)
        docs = await repo.list_documents()
        assert any(d.title == "CT-200 List" for d in docs)
